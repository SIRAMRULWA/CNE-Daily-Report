-- dbt/models/marts/daily_report_records.sql
-- =========================================
-- Grain: one row per (report_date, request_id, task_id)
-- Preserves record-level daily snapshots so selected report dates can drive
-- KPIs, matrix rows, groups, and drill-through records from the same date.
-- A snapshot only consumes staging rows loaded on that same local report date.

{% set report_timezone = env_var('WORKSPACE_TIMEZONE', 'Africa/Johannesburg') %}
{% set local_report_date = "(CURRENT_TIMESTAMP AT TIME ZONE '" ~ report_timezone ~ "')::date" %}

{{ config(
    materialized='incremental',
    unique_key=['report_date', 'request_id', 'task_id'],
    on_schema_change='append_new_columns',
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
)

SELECT
    {{ local_report_date }} AS report_date,
    request_id,
    task_id,
    report_group,
    assignee_group,
    report_category,
    sla_status,
    priority,
    status,
    status_reason,
    assignee,
    summary,
    hours_open,
    create_date,
    assign_time,
    scheduled_start,
    scheduled_end,
    closed_time,
    exclude_change,
    exclude_incident,
    source,
    run_id,
    loaded_at,
    NOW() AS snapshotted_at
FROM active_records
