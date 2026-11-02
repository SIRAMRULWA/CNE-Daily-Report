-- dbt/models/marts/daily_report_summary.sql
-- ==========================================
-- Grain: one row per (report_date, report_group, assignee_group, sla_band)
-- Produces the daily report matrix for every configured division that has
-- eligible active records in staging.raw_changes.
-- Bands:
--   Total Open Calls | Calls Nearing SLA | Breached Calls

{% set report_timezone = env_var('WORKSPACE_TIMEZONE', 'Africa/Johannesburg') %}
{% set local_report_date = "(CURRENT_TIMESTAMP AT TIME ZONE '" ~ report_timezone ~ "')::date" %}

{{ config(
    materialized='incremental',
    unique_key=['report_date', 'report_group', 'assignee_group', 'sla_band'],
    pre_hook="{% if is_incremental() %}DELETE FROM {{ this }} WHERE report_date = " ~ local_report_date ~ "{% endif %}"
) }}

WITH active_records AS (
    SELECT source.*
    FROM {{ ref('stg_changes') }} AS source
    WHERE
        (source.loaded_at AT TIME ZONE '{{ report_timezone }}')::date = {{ local_report_date }}
        AND NOT source.is_excluded
        AND source.report_group IS NOT NULL
        AND source.report_group <> 'Unknown'
        AND source.assignee_group IS NOT NULL
        AND source.assignee_group <> ''
        AND source.report_category IN ('INCIDENT', 'CHANGE', 'ACCESS', 'EVENT')
        AND source.sla_status IN ('WITHIN_SLA', 'NEARING_SLA', 'BREACHED', 'NO_SCHEDULE', 'NO_ASSIGN_TIME')
        AND EXISTS (
            SELECT 1
            FROM config.division_groups AS configured
            WHERE configured.division = source.report_group
              AND configured.assignee_group = source.assignee_group
              AND configured.active
              AND NOT configured.deleted
        )
),

groups AS (
    SELECT DISTINCT
        report_group,
        assignee_group
    FROM active_records
),

bands AS (
    SELECT 'Total Open Calls' AS sla_band, 1 AS sort_order
    UNION ALL
    SELECT 'Calls Nearing SLA' AS sla_band, 2 AS sort_order
    UNION ALL
    SELECT 'Breached Calls' AS sla_band, 3 AS sort_order
),

matrix AS (
    SELECT
        {{ local_report_date }} AS report_date,
        groups.report_group,
        groups.assignee_group,
        bands.sla_band,
        bands.sort_order
    FROM groups
    CROSS JOIN bands
),

counts AS (
    SELECT
        report_group,
        assignee_group,
        CASE
            WHEN sla_status = 'NEARING_SLA' THEN 'Calls Nearing SLA'
            WHEN sla_status = 'BREACHED' THEN 'Breached Calls'
            ELSE 'Total Open Calls'
        END AS sla_band,
        COUNT(*) FILTER (WHERE report_category = 'INCIDENT') AS incident_count,
        COUNT(*) FILTER (WHERE report_category = 'CHANGE') AS change_count,
        COUNT(*) FILTER (WHERE report_category = 'ACCESS') AS access_count,
        COUNT(*) FILTER (WHERE report_category = 'EVENT') AS event_count
    FROM active_records
    GROUP BY
        report_group,
        assignee_group,
        CASE
            WHEN sla_status = 'NEARING_SLA' THEN 'Calls Nearing SLA'
            WHEN sla_status = 'BREACHED' THEN 'Breached Calls'
            ELSE 'Total Open Calls'
        END
),

total_open AS (
    SELECT
        report_group,
        assignee_group,
        'Total Open Calls' AS sla_band,
        COUNT(*) FILTER (WHERE report_category = 'INCIDENT') AS incident_count,
        COUNT(*) FILTER (WHERE report_category = 'CHANGE') AS change_count,
        COUNT(*) FILTER (WHERE report_category = 'ACCESS') AS access_count,
        COUNT(*) FILTER (WHERE report_category = 'EVENT') AS event_count
    FROM active_records
    GROUP BY report_group, assignee_group
),

band_counts AS (
    SELECT * FROM counts WHERE sla_band <> 'Total Open Calls'
    UNION ALL
    SELECT * FROM total_open
)

SELECT
    matrix.report_date,
    matrix.report_group,
    matrix.assignee_group,
    matrix.sla_band,
    COALESCE(band_counts.incident_count, 0) AS incident_count,
    COALESCE(band_counts.change_count, 0) AS change_count,
    COALESCE(band_counts.access_count, 0) AS access_count,
    COALESCE(band_counts.event_count, 0) AS event_count,
    (
        COALESCE(band_counts.incident_count, 0)
        + COALESCE(band_counts.change_count, 0)
        + COALESCE(band_counts.access_count, 0)
        + COALESCE(band_counts.event_count, 0)
    ) AS total_count,
    NOW() AS created_at
FROM matrix
LEFT JOIN band_counts
    ON matrix.report_group = band_counts.report_group
    AND matrix.assignee_group = band_counts.assignee_group
    AND matrix.sla_band = band_counts.sla_band
ORDER BY
    CASE matrix.report_group
        WHEN 'INTSS' THEN 1
        WHEN 'NSD' THEN 2
        WHEN 'CDN' THEN 3
        WHEN 'CVDI' THEN 4
        ELSE 99
    END,
    matrix.report_group,
    matrix.assignee_group,
    matrix.sort_order
