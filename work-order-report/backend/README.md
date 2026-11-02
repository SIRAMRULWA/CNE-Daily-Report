# Work Order Report — Backend

Reports on BMC Helix Work Orders (`WOI:WorkOrder`): which are open, which are
close to their target date, and which are past it. It is a separate app built
from the ITIL Group Reports (Daily Report) backend, with its own database,
users and secrets.

**Late means past the target date.** Open Work Orders get one SLA status:

| SLA status | Rule |
| --- | --- |
| `BREACHED` | now > target date |
| `NEARING_SLA` | target date − 24 h < now ≤ target date |
| `WITHIN_SLA` | now ≤ target date − 24 h |
| `NO_TARGET_DATE` | no target date |

Completed Work Orders are marked `MET_TARGET` or `MISSED_TARGET`. A target date
with no time of day is due at 23:59:59 that day. The 24 h window, the grace
period (0) and the status lists are settings (`WO_*` in `.env.example`).

## Flow

```text
Helix WOI:WorkOrder (or an Excel/CSV export)
   -> pipeline/run.py: extract -> transform (division, type, SLA) -> staging.raw_work_orders
   -> dbt: reporting.wo_report_records / wo_report_summary / wo_completed (one snapshot per day)
   -> FastAPI /api/v1 -> Next.js frontend
```

## Quick start

Use Python 3.12.

```bash
python -m venv venv && . venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # replace every <placeholder>
python -m app_core.migrations # create the schema
python pipeline/run.py --source helix                 # or:
python pipeline/run.py --source file --file data/excel_drop/work_orders.xlsx
uvicorn api.main:app --reload --port 8000
```

`/docs` (interactive API) is available outside production only.

## API (phase 1, 28 operations)

| Area | Endpoints |
| --- | --- |
| Authentication | `/api/v1/auth/sessions`, `/api/v1/users/current` |
| Users and security | `/api/v1/users`, `/api/v1/sessions`, `/api/v1/login-attempts` |
| Divisions | `/api/v1/divisions`, `/api/v1/divisions/{division}/groups`, `/api/v1/division-group-seed-jobs` |
| Work Order report (snapshot) | `/api/v1/daily-reports`, `/api/v1/daily-reports/records` |
| Current Work Orders | `/api/v1/operational-records`, `/api/v1/operational-records/summary` |
| Custom Helix report | `/api/v1/helix-reports`, `/fields`, `/filters` |
| Operations | `/api/v1/health`, `/api/v1/pipeline-runs`, `/api/v1/audit-events` |

The `assignee_group` filter is the team name from the division mapping; in
Work Order data it is the Helix **Support Group Name**.

Report emails and Work Order reminders are phase 2 and are not in this build.

## To confirm before go-live

- Helix field names (target date field especially) against a sample export;
  each is overridable with `WO_*_FIELD` settings.
- Helix status values for open, completed and excluded Work Orders.
- The divisions and support groups that handle Work Orders (the seed list in
  `config/mappings.py` is a copy of the Daily Report teams).
- Read access to `WOI:WorkOrder` for the Helix service account.

## Tests

```bash
python -m pytest -q
cd dbt && dbt test --profiles-dir . --project-dir .
```
