# ITIL Group Reports Automation

Production-oriented Helix reporting platform for current operational data,
immutable Daily Report snapshots, scheduled report delivery, and live
outstanding-task reminders.

The supported API base is `/api/v1`. Use:

- `docs/frontend-api-guide.md` for frontend integration.
- `docs/api-standards.md` for API governance.
- `docs/architecture.md` for module boundaries.
- `docs/pipeline-reporting-lld.md` for extraction and transformation rules.
- `docs/task-reminders.md` for reminder behavior.
- `docs/Production Readiness Package.md` for the current production design.

## Architecture

```text
Helix API or CSV/XLSX
        |
        v
Helix adapters / pipeline extraction
        |
        v
shared ChangeRecord transformation
        |
        +--> live operational APIs and task reminders
        |
        v
staging.raw_changes --> dbt --> reporting snapshot tables
                                      |
                                      v
                         Daily Report APIs and emails

FastAPI / Scheduler / CLI
        |
        v
capability services
        |
        v
PostgreSQL, Helix, and mail adapters
```

Daily Reports read immutable dbt snapshots. Operational-record APIs and task
reminders use current transformed data. Reminders query Helix at execution time
and never update pipeline watermarks, staging data, dbt models, or Daily Report
snapshots.

## Quick start

Use Python 3.12.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Replace all placeholder credentials and secrets in `.env`.

Initialize or upgrade PostgreSQL:

```powershell
python -m app_core.migrations
```

This applies the frozen `sql/001_schema.sql` baseline and subsequent
`sql/migrations/VNNN__description.sql` files. Applied versions and checksums are
stored in `config.schema_migrations`. Never edit an applied migration.

Build the dbt models:

```powershell
dbt run --profiles-dir dbt --project-dir dbt
```

Run the pipeline:

```powershell
# Current Helix extraction
python pipeline/run.py --source helix

# Explicit Helix period
python pipeline/run.py --source helix --helix-period yesterday

# File ingestion
python pipeline/run.py --source file --file "data/excel_drop/helix_export.xlsx"
```

Start the API:

```powershell
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive documentation is available at `http://localhost:8000/docs`;
machine-readable OpenAPI is available at `/api/openapi.json`.

## Supported API areas

| Area | Primary endpoints |
| --- | --- |
| Authentication | `/api/v1/auth/sessions`, `/api/v1/users/current` |
| User administration | `/api/v1/users`, `/api/v1/sessions`, `/api/v1/login-attempts` |
| Current operations | `/api/v1/operational-records`, `/api/v1/operational-records/summary` |
| Daily Report snapshots | `/api/v1/daily-reports`, `/api/v1/daily-reports/records` |
| Divisions | `/api/v1/divisions`, `/api/v1/divisions/{division}/groups` |
| Report delivery | `/api/v1/report-subscriptions`, `/api/v1/report-deliveries` |
| Direct Helix reports | `/api/v1/helix-reports` |
| Task reminders | `/api/v1/task-reminder-subscriptions`, `/api/v1/task-reminder-executions` |
| Operations | `/api/v1/health`, `/api/v1/pipeline-runs`, `/api/v1/audit-events` |

All protected endpoints use `Authorization: Bearer <access_token>`. The
automation-only reminder endpoint is
`POST /api/v1/automation/task-reminder-executions`; frontend applications must
never receive or send `TASK_REMINDER_AUTOMATION_KEY`.

## Power BI and dashboard data

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/daily-reports` | Complete selected-date snapshot, KPIs, and matrix |
| `GET /api/v1/daily-reports/records` | Record-level drill-through from the selected snapshot |
| `GET /api/v1/operational-records` | Current transformed operational tasks |
| `GET /api/v1/operational-records/summary` | Current operational counts and freshness |
| `GET /api/v1/health` | Service and freshness checks |

Do not mix current operational records with historical Daily Report snapshots.

## Business logic

Constants live in `config/mappings.py`; executable classification, SLA, and
eligibility rules live in `pipeline/transform.py`.

### Categories

| Operational category | Report category |
| --- | --- |
| Faults | INCIDENT |
| Change | CHANGE |
| Security or Access | ACCESS |
| Alarm or Failure | EVENT |

Blank categories use request, summary, and notes fallbacks. `INC` tasks are
classified as Security, Alarm, or Faults from their content; `CRQ` maps to
Change. Ordinary Work Orders and PBIs are excluded. A Work Order classified as
Security remains eligible as ACCESS.

### SLA rules

- Changes use Scheduled End plus a 30-minute grace period. Nearing SLA begins
  two hours before that adjusted due time. Missing Scheduled End produces
  `NO_SCHEDULE`.
- Incident, Access, and Event tasks use Assign Time. Nearing SLA begins after
  22 hours and breach occurs after 24 hours. Missing Assign Time produces
  `NO_ASSIGN_TIME`.
- SLA timing is category-based, not priority-based.

### Eligibility

Daily Report and reminder records must have an active mapped division, a
supported report category, an open status, and must not match configured
assignee or Work Order/PBI exclusions. Missing SLA inputs remain visible with
their diagnostic status; they are not automatically removed.

## Email delivery and reminders

Daily Report subscriptions support daily or weekly schedules, recipient and CC
lists, division or group scope, timezone, and CSV/XLSX format. Configuration is
managed through `/api/v1/report-subscriptions`; delivery history and manual
sends use `/api/v1/report-deliveries`.

Task reminders use current live Helix data, the shared transformation rules,
the Daily Report XLSX generator, and an action-oriented email. Admins configure
the schedule and recipients through `/api/v1/task-reminder-subscriptions`.
Normal scheduled delivery is owned by the backend scheduler.

Automated sending remains gated by:

```env
REPORT_EMAIL_AUTOMATION_APPROVED=false
TASK_REMINDER_AUTOMATION_APPROVED=false
```

Enable these only after operational approval.

## Direct Helix reports

`POST /api/v1/helix-reports` is a standalone read-only export facility. It does
not apply Daily Report exclusions or load PostgreSQL/dbt. Field metadata and
active scope filters are exposed by `/api/v1/helix-reports/fields` and
`/api/v1/helix-reports/filters`.

## Project structure

```text
itil-group-reports/
|-- app_core/          # settings, time, auditing, migrations
|-- capabilities/      # organization, reports, reminders
|-- api/               # FastAPI factory, v1 router, HTTP adapters
|-- helix/             # client, query, mapping, enrichment, facade
|-- pipeline/          # extraction, transformation, loading, orchestration
|-- notifications/     # rendering, transport, scheduler adapters
|-- config/            # business constants and default mappings
|-- dbt/               # staging and Daily Report snapshot models
|-- sql/
|   |-- 001_schema.sql # frozen migration baseline
|   `-- migrations/    # forward-only migrations
|-- deploy/            # startup, initialization, pipeline, packaging
|-- docs/              # API, architecture, operations, and LLDs
|-- tests/
|-- Dockerfile
`-- docker-compose.yml
```

## Verification

```powershell
python -m unittest discover -s tests -v
python -m compileall -q api app_core capabilities helix notifications pipeline
```

The OpenAPI contract is generated from `api.app.create_app`; do not maintain
unversioned or undocumented endpoint aliases.
