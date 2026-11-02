# Daily Reports Low-Level Design

## Purpose and scope

Daily Reports expose immutable selected-date snapshots for configured divisions
and assignee groups. Authentication, division maintenance, and pipeline/dbt
generation are documented in their dedicated LLDs.

## Runtime components

| Component | Responsibility |
|---|---|
| `api/v1/router.py` | Public `/api/v1/daily-reports` resources |
| `capabilities/daily_reports/service.py` | Selected-date application use cases |
| `capabilities/daily_reports/repository.py` | Snapshot SQL and response assembly |
| `api/routers/daily_report.py` | HTTP compatibility adapter |
| `reporting.daily_report_summary` | Historical KPI and matrix snapshots |
| `reporting.daily_report_records` | Historical record-level snapshots |
| `config.division_groups` | Active report scope |

## Public API

Only two Daily Report endpoints exist:

| Method and path | Purpose |
|---|---|
| `GET /api/v1/daily-reports` | Complete normal-screen contract |
| `GET /api/v1/daily-reports/records` | Selected-snapshot drill-through records |

Both require at least READ_ONLY access.

### Complete report query

`GET /api/v1/daily-reports` accepts:

| Parameter | Meaning |
|---|---|
| `report_date` | Selected date; defaults to the current application date |
| `period` | `day` or the Monday-Sunday `week` containing the selected date |
| `division` | Exact report division |
| `assignee_group` | Exact mapped group within the division |
| `include_dates` | Include manually selectable historical dates; default `true` |
| `date_limit` | Maximum historical dates, from 1 through 366 |
| `include_records` | Include selected-snapshot records; default `false` |
| `sla` | Optional record expansion filter |
| `category` | Optional record expansion filter |

The response contains one consistent date context, filters, KPI totals, summary
rows, group metadata, optional available dates, and optional records.

### Record drill-through query

`GET /api/v1/daily-reports/records` accepts `report_date`, `period`, `division`,
`assignee_group`, `sla`, and `category`. It reads only
`reporting.daily_report_records` for the selected snapshot window.

## Date and freshness semantics

For `period=day`, `date_from` and `date_to` equal `report_date`. For
`period=week`, they are the surrounding Monday and Sunday.

The selected date applies to KPIs, matrix rows, groups, and records together.
The frontend must not combine report snapshots with current operational data.
An empty current date is authoritative: return empty arrays and zero counts and
do not automatically select a historical date. `available_dates` supports only
explicit user selection.

## KPI and matrix semantics

The summary mart stores one row per report date, division, assignee group, and
SLA band. KPI totals are sums of `total_count` for `Total Open Calls`,
`Calls Nearing SLA`, and `Breached Calls` after the requested filters.

The successful-closures-yesterday KPI comes from its separate prior-24-hour
slice and is never included in open SLA totals. The default boundary is 07:00
inclusive to 07:00 exclusive in `WORKSPACE_TIMEZONE`.

## Error behavior

- Invalid parameters return the standard `422` error contract.
- Database failures use the shared database error handler and `request_id`.
- No rows return a successful empty report rather than historical fallback.
- Unknown or inactive filter values produce empty scoped data unless explicitly
  validated by the handler.

## Verification

```text
GET /api/v1/daily-reports
GET /api/v1/daily-reports?report_date=2026-07-13&include_records=true
GET /api/v1/daily-reports?division=INTSS
GET /api/v1/daily-reports?period=week
GET /api/v1/daily-reports/records?report_date=2026-07-13&division=INTSS
```

Verify that date windows are correct, filters apply consistently, report KPIs
match matrix totals, drill-through uses the same snapshot, and an empty current
date does not load older records.

## Acceptance criteria

- The complete report page loads through one endpoint.
- All active mapped divisions with snapshot data are represented.
- Division and assignee-group filters work independently.
- KPI, matrix, group, and record data use the same selected date/window.
- Current operational APIs are not used as report fallbacks.
- OpenAPI documents only the two supported Daily Report operations.
