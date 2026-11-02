-- dbt/models/marts/wo_report_records.sql
-- ======================================
-- Grain: one row per (report_date, work_order_id).
-- Immutable daily snapshot of every open, in-scope Work Order. It drives the
-- report's totals, grid and drill-through records for that report_date.

{{ config(
    materialized='incremental',
    unique_key=['report_date', 'work_order_id'],
    on_schema_change='append_new_columns',
    pre_hook="{{ replace_today_hook() }}"
) }}

SELECT
    {{ local_report_date() }} AS report_date,
    wo.work_order_id,
    wo.division,
    wo.support_group,
    wo.report_category,
    wo.sla_status,
    wo.priority,
    wo.status,
    wo.status_reason,
    wo.requester,
    wo.assignee,
    wo.summary,
    wo.hours_open,
    wo.days_to_target,
    wo.submit_date,
    wo.target_date,
    wo.completed_date,
    wo.source,
    wo.run_id,
    wo.loaded_at,
    NOW() AS snapshotted_at
FROM {{ ref('stg_work_orders') }} AS wo
WHERE
    {{ loaded_today('wo') }}
    AND wo.is_open
    AND NOT wo.is_excluded
    AND wo.support_group IS NOT NULL
    AND wo.support_group <> ''
    AND wo.sla_status IN ('WITHIN_SLA', 'NEARING_SLA', 'BREACHED', 'NO_TARGET_DATE')
    AND {{ in_active_scope('wo') }}
