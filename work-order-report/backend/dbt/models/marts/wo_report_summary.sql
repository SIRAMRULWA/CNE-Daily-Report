-- dbt/models/marts/wo_report_summary.sql
-- ======================================
-- Grain: one row per (report_date, division, support_group).
-- The report grid: open Work Orders by SLA status for each support group,
-- built from today's wo_report_records snapshot.

{{ config(
    materialized='incremental',
    unique_key=['report_date', 'division', 'support_group'],
    pre_hook="{{ replace_today_hook() }}"
) }}

SELECT
    report_date,
    division,
    support_group,
    COUNT(*) FILTER (WHERE sla_status = 'WITHIN_SLA')     AS within_count,
    COUNT(*) FILTER (WHERE sla_status = 'NEARING_SLA')    AS nearing_count,
    COUNT(*) FILTER (WHERE sla_status = 'BREACHED')       AS breached_count,
    COUNT(*) FILTER (WHERE sla_status = 'NO_TARGET_DATE') AS no_target_count,
    COUNT(*)                                              AS total_open,
    NOW()                                                 AS created_at
FROM {{ ref('wo_report_records') }}
WHERE report_date = {{ local_report_date() }}
GROUP BY report_date, division, support_group
