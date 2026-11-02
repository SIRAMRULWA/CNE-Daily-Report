-- Every saved record must belong to the same local date as its report snapshot.
-- Any returned row fails this dbt data test.

SELECT
    report_date,
    work_order_id,
    loaded_at
FROM {{ ref('wo_report_records') }}
WHERE (loaded_at AT TIME ZONE '{{ report_timezone() }}')::date <> report_date
