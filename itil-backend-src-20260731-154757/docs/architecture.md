# Application Architecture

## Direction

The platform is being evolved incrementally as a modular monolith. Existing
`/api/v1` contracts, environment variables, database tables, scheduler
commands, report outputs, and deployment entrypoints remain compatible during
the migration.

The intended dependency direction is:

```text
API / CLI / Scheduler
        |
        v
Application use cases
        |
        v
Domain rules
        ^
        |
Infrastructure adapters (PostgreSQL, Helix, SMTP)
```

Code outside `api` must not import the API package. Delivery-neutral
foundations are placed in `app_core`; capability-specific modules will be
introduced behind existing public functions before callers are migrated.

## Current foundations

- `app_core.settings` provides immutable typed settings while retaining the
  existing environment-variable contract.
- `app_core.clock` owns UTC and workspace-local time conversion.
- `app_core.audit` records audit events for HTTP, scheduler, pipeline, and
  future worker entrypoints without importing FastAPI.
- `api.auth.audit_event` remains a compatibility export during migration.
- `capabilities.organization` owns division/group application behavior and
  PostgreSQL persistence. `pipeline.division_groups` remains a compatibility
  facade for existing Helix, transformation, reminder, and reporting callers.
- `capabilities.report_delivery` owns Daily Report subscription policy,
  persistence, manual delivery orchestration, and delivery history. The
  report-email router is an HTTP-only adapter.
- `app_core.recipients` owns shared address normalization and recipient-domain
  policy. Report-email and task-reminder routers do not import one another.
- `capabilities.task_reminders` owns reminder subscriptions, execution
  history, idempotent claims, live Helix execution, delivery state, and audit
  transitions. The API router and scheduler are thin entrypoint adapters, and
  `notifications.task_reminders.execute` remains a compatibility function.
- `helix.client`, `helix.query`, `helix.mapper`, `helix.datetime_utils`, and
  `helix.enrichment` own the external Helix concerns. `HelixExtractor` remains
  the compatibility facade and extraction orchestrator for existing pipeline,
  raw-report, and reminder callers.
- `capabilities.daily_reports` owns immutable snapshot SQL, selected-date
  response assembly, KPI/summary/group/record access, and email snapshot data.
  The API and notification modules are compatibility/delivery adapters with no
  direct database access.
- `app_core.migrations` owns ordered schema upgrades, advisory locking,
  immutable checksums, and migration history. Deployment applies migrations
  before dbt or application traffic; ordinary requests do not create tables.
  The container startup script verifies/applies migrations before launching
  Uvicorn, and `deploy/init-db.sh` performs the same idempotent check before
  running dbt.

## Change rules

1. Refactors must preserve the OpenAPI contract unless an API change is
   explicitly approved and versioned.
2. Database changes are additive first. Destructive changes require a later,
   independently deployable cleanup release.
3. Old entrypoints remain as compatibility wrappers until all callers have
   migrated and a stable release has passed.
4. New workflows are disabled by default and activated separately from code
   deployment.
5. Daily Report snapshots remain isolated from live reminder and extraction
   workflows.
6. Scheduled or manual background operations must be idempotent and auditable.
7. Every phase must pass unit tests, API-contract tests, compilation, and
   deployment smoke checks before release.
8. `sql/001_schema.sql` is the frozen baseline. New schema changes use
   `sql/migrations/VNNN__description.sql` and applied files are never edited.
9. Operational report payloads have a seven-day retention window. The purge
   implementation is an explicit allowlist and must preserve audit events,
   login/security history, configuration, delivery/execution history,
   watermarks, and pipeline-run metadata.

`RUNTIME_SCHEMA_BOOTSTRAP_ENABLED=true` temporarily restores the legacy
runtime table-creation behavior for controlled recovery. It defaults to
`false` and should remain disabled in normal environments.

## Refactoring status and next phases

Completed:

1. Foundations, typed settings, shared clock, audit, and characterization tests.
2. Organization, report-delivery, task-reminder, and Daily Report capability
   boundaries with SQL removed from HTTP adapters.
3. Helix client, query, mapper, datetime, and enrichment separation behind
   `HelixExtractor`.
4. Shared notification rendering, scheduling, recipient policy, and delivery
   services.
5. Versioned database migrations, checksum history, advisory locking, and
   migration-before-API startup.

Planned:

1. Separate API and worker runtime roles using the same application image.
2. Configurable extraction profiles for additional Helix use cases.
3. Remove compatibility facades only after all callers have migrated and a
   stable release has passed.
