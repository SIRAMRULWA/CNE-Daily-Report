-- dbt/models/staging/stg_work_orders.sql
-- ======================================
-- Grain: one row per work_order_id (raw_work_orders is already unique).
-- Normalises text values and derives boolean flags used by the marts.

{{ config(materialized='view') }}

SELECT
    work_order_id,
    TRIM(summary)                        AS summary,
    report_category,
    TRIM(status)                         AS status,
    TRIM(status_reason)                  AS status_reason,
    INITCAP(TRIM(priority))              AS priority,
    TRIM(requester)                      AS requester,
    TRIM(support_group)                  AS support_group,
    TRIM(assignee)                       AS assignee,

    submit_date,
    target_date,
    completed_date,
    last_modified,

    division,
    sla_status,
    ROUND(hours_open::NUMERIC, 2)        AS hours_open,
    days_to_target,
    is_open,
    is_excluded,

    sla_status = 'BREACHED'              AS is_breached,
    sla_status = 'NEARING_SLA'           AS is_nearing,
    sla_status = 'WITHIN_SLA'            AS is_within_sla,
    sla_status = 'NO_TARGET_DATE'        AS has_no_target_date,

    source,
    run_id,
    loaded_at
FROM staging.raw_work_orders
