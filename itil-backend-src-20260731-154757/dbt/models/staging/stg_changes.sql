-- dbt/models/staging/stg_changes.sql
-- ===================================
-- Grain: one row per (request_id, task_id)
-- Deduplicates raw_changes by keeping the most recent load per task.
-- Normalises status values and derives boolean operational flags.

{{ config(materialized='view') }}

WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY request_id, task_id
            ORDER BY loaded_at DESC
        ) AS rn
    FROM staging.raw_changes
),

deduped AS (
    SELECT * FROM ranked WHERE rn = 1
),

normalised AS (
    SELECT
        -- identifiers
        request_id,
        task_id,
        LEFT(request_id, 3)                              AS request_prefix,

        -- source fields
        op_cat_tier1,
        TRIM(summary)                                    AS summary,
        TRIM(assignee)                                   AS assignee,
        INITCAP(TRIM(priority))                          AS priority,
        TRIM(status)                                     AS status,
        TRIM(status_reason)                              AS status_reason,
        TRIM(assignee_group)                             AS assignee_group,
        notes,

        -- timestamps
        create_date,
        assign_time,
        closed_time,
        scheduled_start,
        scheduled_end,

        -- derived classification
        report_group,
        report_category,
        sla_status,
        ROUND(hours_open::NUMERIC, 2)                   AS hours_open,
        exclude_change,
        exclude_incident,
        (exclude_change OR exclude_incident)             AS is_excluded,

        -- boolean operational flags
        status IN ('Closed','Cancelled','Success','Bypassed') AS is_closed,
        status IN ('Assigned','Staged','Work in Progress','Work In Progress','Pending')
            AND NOT (exclude_change OR exclude_incident)      AS is_active,
        sla_status = 'BREACHED'                               AS is_breached,
        sla_status = 'NEARING_SLA'                            AS is_nearing,
        sla_status = 'WITHIN_SLA'                             AS is_within_sla,
        sla_status = 'NO_SCHEDULE'                            AS has_no_schedule,
        sla_status = 'NO_ASSIGN_TIME'                         AS has_no_assign_time,

        -- metadata
        source,
        run_id,
        loaded_at

    FROM deduped
)

SELECT * FROM normalised
