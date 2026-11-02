-- Attachment-only record-level changes closed in the prior 24-hour window.
-- All outcomes are retained; the existing success KPI remains unchanged.
{% set report_timezone = env_var('WORKSPACE_TIMEZONE', 'Africa/Johannesburg') %}
{% set local_report_date = "(CURRENT_TIMESTAMP AT TIME ZONE '" ~ report_timezone ~ "')::date" %}
{% set schedule_hour = env_var('PIPELINE_SCHEDULE_HOUR', '7') | int %}

{{ config(
    materialized='incremental',
    unique_key=['report_date', 'request_id', 'task_id'],
    on_schema_change='append_new_columns',
    pre_hook="{% if is_incremental() %}DELETE FROM {{ this }} WHERE report_date = " ~ local_report_date ~ "{% endif %}"
) }}

SELECT
    {{ local_report_date }} AS report_date,
    request_id, task_id, report_group, assignee_group, report_category,
    sla_status, priority, status, status_reason, assignee, summary, hours_open,
    create_date, assign_time, scheduled_start, scheduled_end, closed_time,
    source, run_id, loaded_at, NOW() AS snapshotted_at
FROM {{ ref('stg_changes') }} AS source
WHERE
    (source.loaded_at AT TIME ZONE '{{ report_timezone }}')::date = {{ local_report_date }}
    AND (source.closed_time AT TIME ZONE '{{ report_timezone }}') >=
        ({{ local_report_date }} - 1)::timestamp + INTERVAL '{{ schedule_hour }} hours'
    AND (source.closed_time AT TIME ZONE '{{ report_timezone }}') <
        {{ local_report_date }}::timestamp + INTERVAL '{{ schedule_hour }} hours'
    AND source.report_category = 'CHANGE'
    AND source.report_group IS NOT NULL
    AND source.report_group <> 'Unknown'
    AND source.assignee_group IS NOT NULL
    AND source.assignee_group <> ''
    AND EXISTS (
        SELECT 1 FROM config.division_groups AS configured
        WHERE configured.division = source.report_group
          AND configured.assignee_group = source.assignee_group
          AND configured.active AND NOT configured.deleted
    )
