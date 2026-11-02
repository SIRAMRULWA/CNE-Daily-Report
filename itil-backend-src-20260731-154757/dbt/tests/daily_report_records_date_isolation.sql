-- Every saved record must belong to the same local date as its report snapshot.
-- Any returned row fails this dbt data test.

SELECT
    report_date,
    request_id,
    task_id,
    loaded_at
FROM {{ ref('daily_report_records') }}
WHERE
    (loaded_at AT TIME ZONE '{{ env_var("WORKSPACE_TIMEZONE", "Africa/Johannesburg") }}')::date
    <> report_date
