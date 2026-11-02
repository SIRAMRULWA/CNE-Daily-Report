-- dbt/models/marts/wo_completed.sql
-- =================================
-- Grain: one row per (report_date, work_order_id).
-- Work Orders completed in the previous scheduled window (07:00 yesterday to
-- 07:00 today by default), each marked MET_TARGET, MISSED_TARGET or
-- NO_TARGET_DATE. Kept apart from the open-Work-Order counts.

{{ config(
    materialized='incremental',
    unique_key=['report_date', 'work_order_id'],
    pre_hook="{{ replace_today_hook() }}"
) }}

SELECT
    {{ local_report_date() }}                          AS report_date,
    {{ completion_window_end() }} - INTERVAL '1 day'   AS window_start,
    {{ completion_window_end() }}                      AS window_end,
    wo.work_order_id,
    wo.division,
    wo.support_group,
    wo.report_category,
    wo.sla_status,
    wo.priority,
    wo.status,
    wo.requester,
    wo.assignee,
    wo.summary,
    wo.hours_open,
    wo.days_to_target,
    wo.submit_date,
    wo.target_date,
    wo.completed_date,
    NOW() AS snapshotted_at
FROM {{ ref('stg_work_orders') }} AS wo
WHERE
    {{ loaded_today('wo') }}
    AND NOT wo.is_open
    AND NOT wo.is_excluded
    AND wo.sla_status IN ('MET_TARGET', 'MISSED_TARGET', 'NO_TARGET_DATE')
    AND wo.completed_date >= {{ completion_window_end() }} - INTERVAL '1 day'
    AND wo.completed_date <  {{ completion_window_end() }}
    AND {{ in_active_scope('wo') }}
