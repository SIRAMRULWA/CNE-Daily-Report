-- Successful closures from the prior local day, captured by the morning run.
-- Grain: one row per (report_date, closure_date, report_group, assignee_group).

{% set report_timezone = env_var('WORKSPACE_TIMEZONE', 'Africa/Johannesburg') %}
{% set local_report_date = "(CURRENT_TIMESTAMP AT TIME ZONE '" ~ report_timezone ~ "')::date" %}
{% set schedule_hour = env_var('PIPELINE_SCHEDULE_HOUR', '7') | int %}

{{ config(
    materialized='incremental',
    unique_key=['report_date', 'closure_date', 'report_group', 'assignee_group'],
    on_schema_change='append_new_columns',
    pre_hook="{% if is_incremental() %}DELETE FROM {{ this }} WHERE report_date = " ~ local_report_date ~ "{% endif %}"
) }}

WITH successful_closures AS (
    SELECT source.*
    FROM {{ ref('stg_changes') }} AS source
    WHERE
        (source.loaded_at AT TIME ZONE '{{ report_timezone }}')::date = {{ local_report_date }}
        AND (source.closed_time AT TIME ZONE '{{ report_timezone }}') >=
            ({{ local_report_date }} - 1)::timestamp + INTERVAL '{{ schedule_hour }} hours'
        AND (source.closed_time AT TIME ZONE '{{ report_timezone }}') <
            {{ local_report_date }}::timestamp + INTERVAL '{{ schedule_hour }} hours'
        AND UPPER(TRIM(COALESCE(source.status_reason, ''))) = 'SUCCESS'
        AND source.report_group IS NOT NULL
        AND source.report_group <> 'Unknown'
        AND source.assignee_group IS NOT NULL
        AND source.assignee_group <> ''
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
    {{ local_report_date }} - 1 AS closure_date,
    (
        ({{ local_report_date }} - 1)::timestamp + INTERVAL '{{ schedule_hour }} hours'
    ) AT TIME ZONE '{{ report_timezone }}' AS window_start,
    (
        {{ local_report_date }}::timestamp + INTERVAL '{{ schedule_hour }} hours'
    ) AT TIME ZONE '{{ report_timezone }}' AS window_end,
    report_group,
    assignee_group,
    COUNT(*) FILTER (WHERE report_category = 'INCIDENT') AS incident_count,
    COUNT(*) FILTER (WHERE report_category = 'CHANGE') AS change_count,
    COUNT(*) FILTER (WHERE report_category = 'ACCESS') AS access_count,
    COUNT(*) FILTER (WHERE report_category = 'EVENT') AS event_count,
    COUNT(*) AS total_count,
    NOW() AS created_at
FROM successful_closures
GROUP BY report_group, assignee_group
