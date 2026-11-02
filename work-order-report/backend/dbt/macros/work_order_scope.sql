{# Shared snapshot helpers for the Work Order marts. #}

{% macro report_timezone() -%}
    {{ env_var('WORKSPACE_TIMEZONE', 'Africa/Johannesburg') }}
{%- endmacro %}

{# Today's date in the workspace time zone: the report_date of this run. #}
{% macro local_report_date() -%}
    (CURRENT_TIMESTAMP AT TIME ZONE '{{ report_timezone() }}')::date
{%- endmacro %}

{# Rows loaded by today's pipeline run only, so each snapshot is one day. #}
{% macro loaded_today(alias) -%}
    ({{ alias }}.loaded_at AT TIME ZONE '{{ report_timezone() }}')::date = {{ local_report_date() }}
{%- endmacro %}

{# The support group is still mapped to its division and active. #}
{% macro in_active_scope(alias) -%}
    EXISTS (
        SELECT 1
        FROM config.division_groups AS configured
        WHERE configured.division = {{ alias }}.division
          AND configured.assignee_group = {{ alias }}.support_group
          AND configured.active
          AND NOT configured.deleted
    )
{%- endmacro %}

{# End of the completed-yesterday window: today at PIPELINE_SCHEDULE_HOUR. #}
{% macro completion_window_end() -%}
    ({{ local_report_date() }} + make_interval(hours => {{ env_var('PIPELINE_SCHEDULE_HOUR', '7') | int }}))
{%- endmacro %}

{# Replace today's snapshot when the pipeline is re-run on the same day. #}
{% macro replace_today_hook() -%}
    {% if is_incremental() %}DELETE FROM {{ this }} WHERE report_date = {{ local_report_date() }}{% endif %}
{%- endmacro %}
