/*
ITIL Group Reports - Grafana/PostgreSQL monitoring queries

Recommended dashboard refresh: 1 minute
Expected pipeline interval: 30 minutes
The 45-minute stale threshold allows 15 minutes for a delayed run.

Do not give the Grafana database user access to raw_payload, password_hash,
session tokens, recipient addresses, or other sensitive columns.
*/

-- ============================================================================
-- MAIN PANEL A: System health banner (Stat)
-- Value mapping: HEALTHY=green, ATTENTION REQUIRED=amber, CRITICAL=red.
-- ============================================================================
WITH health AS (
    SELECT
        CASE
            WHEN last_run_at IS NULL
              OR NOW() - last_run_at > INTERVAL '45 minutes'
              OR last_run_status NOT IN ('SUCCESS', 'PARTIAL')
                THEN 2
            WHEN NOW() - last_run_at > INTERVAL '35 minutes'
              OR last_run_status = 'PARTIAL'
                THEN 1
            ELSE 0
        END AS level
    FROM reporting.pipeline_heartbeat
    WHERE id = 1

    UNION ALL

    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM staging.elt_run_log
            WHERE status = 'FAILED'
              AND run_start >= NOW() - INTERVAL '24 hours'
        ) THEN 2 ELSE 0
    END

    UNION ALL

    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM reporting.report_email_deliveries
            WHERE status = 'FAILED'
              AND started_at >= NOW() - INTERVAL '24 hours'
        ) OR EXISTS (
            SELECT 1 FROM reporting.task_reminder_executions
            WHERE status = 'FAILED'
              AND started_at >= NOW() - INTERVAL '24 hours'
        ) THEN 2 ELSE 0
    END
)
SELECT CASE MAX(level)
    WHEN 2 THEN 'CRITICAL'
    WHEN 1 THEN 'ATTENTION REQUIRED'
    ELSE 'HEALTHY'
END AS system_health
FROM health;


-- ============================================================================
-- MAIN PANELS B-E: Four KPI cards (Stat)
-- In Grafana, use one query per card so each can have its own unit/threshold.
-- ============================================================================

-- B: Last refresh age. Unit: minutes. Thresholds: 35 amber, 45 red.
SELECT
    COALESCE(
        ROUND(EXTRACT(EPOCH FROM (NOW() - last_run_at)) / 60),
        -1
    ) AS minutes_since_refresh
FROM reporting.pipeline_heartbeat
WHERE id = 1;

-- C: Failed/partial pipeline runs. Thresholds: 1 amber, 2 red.
SELECT COUNT(*) AS unhealthy_runs
FROM staging.elt_run_log
WHERE run_start >= NOW() - INTERVAL '24 hours'
  AND status IN ('FAILED', 'PARTIAL');

-- D: Current breached items. Threshold: 1 red.
SELECT COUNT(*) AS breached_items
FROM reporting.daily_report_records
WHERE report_date = (
    SELECT MAX(report_date) FROM reporting.daily_report_records
)
  AND sla_status = 'BREACHED';

-- E: Failed notifications. Threshold: 1 red.
SELECT
    (
        SELECT COUNT(*)
        FROM reporting.report_email_deliveries
        WHERE started_at >= NOW() - INTERVAL '24 hours'
          AND status = 'FAILED'
    )
    +
    (
        SELECT COUNT(*)
        FROM reporting.task_reminder_executions
        WHERE started_at >= NOW() - INTERVAL '24 hours'
          AND status = 'FAILED'
    ) AS failed_notifications;


-- ============================================================================
-- MAIN PANEL F: Pipeline health (Time series)
-- Loaded=green line; rejected=red bars.
-- ============================================================================
SELECT
    $__timeGroupAlias(run_start, '30m'),
    SUM(rows_loaded) AS "Loaded",
    SUM(rows_rejected) AS "Rejected"
FROM staging.elt_run_log
WHERE $__timeFilter(run_start)
GROUP BY 1
ORDER BY 1;


-- ============================================================================
-- MAIN PANEL G: SLA risk by team (Horizontal stacked bar chart)
-- Breached=red; Nearing SLA=amber. Limit keeps the chart readable.
-- ============================================================================
SELECT
    assignee_group AS team,
    COUNT(*) FILTER (WHERE sla_status = 'BREACHED') AS "Breached",
    COUNT(*) FILTER (WHERE sla_status = 'NEARING_SLA') AS "Nearing SLA"
FROM reporting.daily_report_records
WHERE report_date = (
        SELECT MAX(report_date) FROM reporting.daily_report_records
    )
  AND report_group LIKE '$division'
  AND assignee_group LIKE '$assignee_group'
  AND sla_status IN ('BREACHED', 'NEARING_SLA')
GROUP BY assignee_group
HAVING COUNT(*) > 0
ORDER BY "Breached" DESC, "Nearing SLA" DESC
LIMIT 10;


-- ============================================================================
-- MAIN PANEL H: What needs action now (one Table)
-- Transform: colour severity; hide event_time if desired.
-- ============================================================================
WITH actions AS (
    SELECT
        CASE WHEN sla_status = 'BREACHED' THEN 1 ELSE 2 END AS sort_order,
        CASE WHEN sla_status = 'BREACHED' THEN 'CRITICAL' ELSE 'WARNING' END
            AS severity,
        report_group AS division,
        assignee_group AS team,
        COUNT(*) AS affected,
        CASE
            WHEN sla_status = 'BREACHED' THEN 'SLA has been breached'
            ELSE 'SLA deadline is approaching'
        END AS problem,
        CASE
            WHEN sla_status = 'BREACHED' THEN 'Assign an owner and act immediately'
            ELSE 'Review and action before the SLA deadline'
        END AS next_action,
        MAX(loaded_at) AS event_time
    FROM reporting.daily_report_records
    WHERE report_date = (
            SELECT MAX(report_date) FROM reporting.daily_report_records
        )
      AND report_group LIKE '$division'
      AND assignee_group LIKE '$assignee_group'
      AND sla_status IN ('BREACHED', 'NEARING_SLA')
    GROUP BY report_group, assignee_group, sla_status

    UNION ALL

    SELECT
        1,
        'CRITICAL',
        COALESCE(s.division, 'SYSTEM'),
        COALESCE(s.assignee_group, 'Notifications'),
        COUNT(*),
        'Report email delivery failed',
        'Check the provider error and retry the delivery',
        MAX(d.started_at)
    FROM reporting.report_email_deliveries d
    LEFT JOIN config.report_email_subscriptions s ON s.id = d.subscription_id
    WHERE d.started_at >= NOW() - INTERVAL '24 hours'
      AND d.status = 'FAILED'
    GROUP BY s.division, s.assignee_group

    UNION ALL

    SELECT
        1,
        'CRITICAL',
        'SYSTEM',
        source_entity,
        COUNT(*),
        'Pipeline run failed',
        'Inspect the latest run error and application logs',
        MAX(run_start)
    FROM staging.elt_run_log
    WHERE run_start >= NOW() - INTERVAL '24 hours'
      AND status = 'FAILED'
    GROUP BY source_entity
)
SELECT
    severity,
    division,
    team,
    affected,
    problem,
    next_action,
    event_time
FROM actions
ORDER BY sort_order, affected DESC, event_time DESC;


-- Everything below this point belongs in a collapsed "Diagnostics" row.

-- ============================================================================
-- PANEL 1: Current health (Table)
-- This is the main "what is wrong?" panel. Show rows where severity <> 'OK'.
-- Suggested value colours: OK=green, WARNING=yellow, CRITICAL=red.
-- ============================================================================
WITH latest_run AS (
    SELECT
        run_id,
        status,
        run_start,
        run_end,
        rows_extracted,
        rows_loaded,
        rows_rejected,
        error_message
    FROM staging.elt_run_log
    ORDER BY run_start DESC
    LIMIT 1
),
signals AS (
    SELECT
        'Pipeline freshness'::text AS check_name,
        CASE
            WHEN h.last_run_at IS NULL THEN 'CRITICAL'
            WHEN NOW() - h.last_run_at > INTERVAL '45 minutes' THEN 'CRITICAL'
            WHEN NOW() - h.last_run_at > INTERVAL '35 minutes' THEN 'WARNING'
            ELSE 'OK'
        END AS severity,
        COALESCE(
            ROUND(EXTRACT(EPOCH FROM (NOW() - h.last_run_at)) / 60)::text
                || ' minutes since last completed cycle',
            'Pipeline has never completed'
        ) AS what_is_wrong,
        'Check the pipeline cron/container and Helix or database connectivity'
            AS team_action,
        h.last_run_at AS event_time
    FROM reporting.pipeline_heartbeat h
    WHERE h.id = 1

    UNION ALL

    SELECT
        'Latest pipeline run',
        CASE
            WHEN r.status = 'FAILED' THEN 'CRITICAL'
            WHEN r.status IN ('PARTIAL', 'RUNNING') THEN 'WARNING'
            ELSE 'OK'
        END,
        CASE
            WHEN r.status = 'SUCCESS' THEN
                'Run succeeded: ' || r.rows_loaded || ' rows loaded'
            ELSE
                'Run ' || r.run_id || ' is ' || r.status
                || COALESCE(': ' || NULLIF(LEFT(r.error_message, 300), ''), '')
        END,
        CASE
            WHEN r.status = 'FAILED' THEN
                'Use the run ID to inspect application logs and fix the reported error'
            WHEN r.status = 'PARTIAL' THEN
                'Review rejected rows and the failed source entity'
            WHEN r.status = 'RUNNING'
                 AND NOW() - r.run_start > INTERVAL '45 minutes' THEN
                'Run may be stuck; inspect the application container and database activity'
            ELSE 'No action required'
        END,
        r.run_start
    FROM latest_run r

    UNION ALL

    SELECT
        'Rejected source records',
        CASE
            WHEN COALESCE(r.rows_rejected, 0) >= 10 THEN 'CRITICAL'
            WHEN COALESCE(r.rows_rejected, 0) > 0 THEN 'WARNING'
            ELSE 'OK'
        END,
        COALESCE(r.rows_rejected, 0)::text
            || ' records rejected in run ' || r.run_id,
        CASE
            WHEN COALESCE(r.rows_rejected, 0) > 0 THEN
                'Open the rejected-records panel and correct the source data'
            ELSE 'No action required'
        END,
        r.run_start
    FROM latest_run r

    UNION ALL

    SELECT
        'Report email delivery',
        CASE
            WHEN COUNT(*) FILTER (WHERE status = 'FAILED') > 0 THEN 'CRITICAL'
            WHEN COUNT(*) FILTER (
                WHERE status = 'SENDING'
                  AND started_at < NOW() - INTERVAL '15 minutes'
            ) > 0 THEN 'WARNING'
            ELSE 'OK'
        END,
        COUNT(*) FILTER (WHERE status = 'FAILED')::text
            || ' failed and '
            || COUNT(*) FILTER (
                WHERE status = 'SENDING'
                  AND started_at < NOW() - INTERVAL '15 minutes'
            )::text || ' stuck in the last 24 hours',
        'Check mail-provider connectivity, subscription configuration, and the delivery error',
        MAX(started_at)
    FROM reporting.report_email_deliveries
    WHERE started_at >= NOW() - INTERVAL '24 hours'

    UNION ALL

    SELECT
        'Task reminder delivery',
        CASE
            WHEN COUNT(*) FILTER (WHERE status = 'FAILED') > 0 THEN 'CRITICAL'
            WHEN COUNT(*) FILTER (
                WHERE status = 'RUNNING'
                  AND started_at < NOW() - INTERVAL '15 minutes'
            ) > 0 THEN 'WARNING'
            ELSE 'OK'
        END,
        COUNT(*) FILTER (WHERE status = 'FAILED')::text
            || ' failed and '
            || COUNT(*) FILTER (
                WHERE status = 'RUNNING'
                  AND started_at < NOW() - INTERVAL '15 minutes'
            )::text || ' stuck in the last 24 hours',
        'Check mail-provider connectivity and the reminder execution error',
        MAX(started_at)
    FROM reporting.task_reminder_executions
    WHERE started_at >= NOW() - INTERVAL '24 hours'
)
SELECT
    severity,
    check_name,
    what_is_wrong,
    team_action,
    event_time
FROM signals
ORDER BY
    CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'WARNING' THEN 2 ELSE 3 END,
    check_name;


-- ============================================================================
-- PANEL 2: Pipeline run history (Table)
-- ============================================================================
SELECT
    run_start AS "time",
    run_id,
    pipeline_name,
    source_entity,
    status,
    rows_extracted,
    rows_loaded,
    rows_rejected,
    EXTRACT(EPOCH FROM (COALESCE(run_end, NOW()) - run_start))::int
        AS duration_seconds,
    LEFT(error_message, 500) AS error_message
FROM staging.elt_run_log
WHERE $__timeFilter(run_start)
ORDER BY run_start DESC;


-- ============================================================================
-- PANEL 3: Pipeline failures over time (Time series)
-- Alert when the FAILED or PARTIAL series is above zero for 5 minutes.
-- ============================================================================
SELECT
    $__timeGroupAlias(run_start, '5m'),
    status AS metric,
    COUNT(*) AS value
FROM staging.elt_run_log
WHERE $__timeFilter(run_start)
  AND status IN ('FAILED', 'PARTIAL')
GROUP BY 1, status
ORDER BY 1;


-- ============================================================================
-- PANEL 4: Rejected records with a safe reason (Table)
-- Deliberately excludes raw_data because it may contain sensitive source data.
-- ============================================================================
SELECT
    rr.rejected_at AS "time",
    rr.run_id,
    rr.source_entity,
    rr.rejection_reason
FROM staging.elt_rejected_records rr
WHERE $__timeFilter(rr.rejected_at)
ORDER BY rr.rejected_at DESC;


-- ============================================================================
-- PANEL 5: Teams requiring attention now (Table)
-- Use dashboard variables $division and $assignee_group, each with Include All.
-- Configure the All value as: %
-- ============================================================================
SELECT
    report_group AS division,
    assignee_group,
    COUNT(*) AS open_items,
    COUNT(*) FILTER (WHERE sla_status = 'BREACHED') AS breached,
    COUNT(*) FILTER (WHERE sla_status = 'NEARING_SLA') AS nearing_sla,
    COUNT(*) FILTER (
        WHERE sla_status IN ('NO_SCHEDULE', 'NO_ASSIGN_TIME')
    ) AS missing_sla_data,
    ROUND(MAX(hours_open), 1) AS oldest_hours_open,
    CASE
        WHEN COUNT(*) FILTER (WHERE sla_status = 'BREACHED') > 0
            THEN 'CRITICAL: assign an owner and action breached items'
        WHEN COUNT(*) FILTER (WHERE sla_status = 'NEARING_SLA') > 0
            THEN 'WARNING: act before the SLA deadline'
        WHEN COUNT(*) FILTER (
            WHERE sla_status IN ('NO_SCHEDULE', 'NO_ASSIGN_TIME')
        ) > 0
            THEN 'WARNING: correct missing schedule/assignment data'
        ELSE 'OK'
    END AS team_action
FROM reporting.daily_report_records
WHERE report_date = (
        SELECT MAX(report_date) FROM reporting.daily_report_records
    )
  AND report_group LIKE '$division'
  AND assignee_group LIKE '$assignee_group'
GROUP BY report_group, assignee_group
ORDER BY breached DESC, nearing_sla DESC, missing_sla_data DESC, open_items DESC;


-- ============================================================================
-- PANEL 6: Ticket drill-down for the selected team (Table)
-- ============================================================================
SELECT
    request_id,
    task_id,
    report_category,
    priority,
    status,
    sla_status,
    assignee,
    ROUND(hours_open, 1) AS hours_open,
    scheduled_end,
    CASE
        WHEN sla_status = 'BREACHED' THEN 'SLA breached - action immediately'
        WHEN sla_status = 'NEARING_SLA' THEN 'SLA at risk - action today'
        WHEN sla_status = 'NO_SCHEDULE' THEN 'Scheduled end is missing'
        WHEN sla_status = 'NO_ASSIGN_TIME' THEN 'Assignment time is missing'
        ELSE 'Monitor'
    END AS what_is_wrong
FROM reporting.daily_report_records
WHERE report_date = (
        SELECT MAX(report_date) FROM reporting.daily_report_records
    )
  AND report_group LIKE '$division'
  AND assignee_group LIKE '$assignee_group'
  AND sla_status IN ('BREACHED', 'NEARING_SLA', 'NO_SCHEDULE', 'NO_ASSIGN_TIME')
ORDER BY
    CASE sla_status
        WHEN 'BREACHED' THEN 1
        WHEN 'NEARING_SLA' THEN 2
        WHEN 'NO_ASSIGN_TIME' THEN 3
        ELSE 4
    END,
    hours_open DESC NULLS LAST;


-- ============================================================================
-- PANEL 7: Failed/stuck notifications (Table)
-- Does not display recipient addresses.
-- ============================================================================
SELECT
    'REPORT_EMAIL' AS notification_type,
    d.started_at AS "time",
    d.id AS execution_id,
    s.name AS subscription,
    s.division,
    s.assignee_group,
    d.status,
    LEFT(d.error_message, 500) AS error_message,
    CASE
        WHEN d.status = 'FAILED' THEN 'Check provider/configuration and retry'
        ELSE 'Execution has been running over 15 minutes; inspect worker logs'
    END AS team_action
FROM reporting.report_email_deliveries d
LEFT JOIN config.report_email_subscriptions s ON s.id = d.subscription_id
WHERE $__timeFilter(d.started_at)
  AND (
      d.status = 'FAILED'
      OR (d.status = 'SENDING' AND d.started_at < NOW() - INTERVAL '15 minutes')
  )

UNION ALL

SELECT
    'TASK_REMINDER',
    e.started_at,
    e.id,
    s.name,
    s.division,
    s.assignee_group,
    e.status,
    LEFT(
        CONCAT_WS(': ', NULLIF(e.error_code, ''), NULLIF(e.error_message, '')),
        500
    ),
    CASE
        WHEN e.status = 'FAILED' THEN 'Check provider/configuration and retry'
        ELSE 'Execution has been running over 15 minutes; inspect worker logs'
    END
FROM reporting.task_reminder_executions e
JOIN config.task_reminder_subscriptions s ON s.id = e.subscription_id
WHERE $__timeFilter(e.started_at)
  AND (
      e.status = 'FAILED'
      OR (e.status = 'RUNNING' AND e.started_at < NOW() - INTERVAL '15 minutes')
  )
ORDER BY "time" DESC;


-- ============================================================================
-- GRAFANA VARIABLE: division
-- ============================================================================
SELECT '%' AS __value, 'All' AS __text
UNION ALL
SELECT DISTINCT report_group AS __value, report_group AS __text
FROM reporting.daily_report_records
ORDER BY __text;


-- ============================================================================
-- GRAFANA VARIABLE: assignee_group
-- ============================================================================
SELECT '%' AS __value, 'All' AS __text
UNION ALL
SELECT DISTINCT assignee_group AS __value, assignee_group AS __text
FROM reporting.daily_report_records
WHERE report_group LIKE '$division'
ORDER BY __text;
