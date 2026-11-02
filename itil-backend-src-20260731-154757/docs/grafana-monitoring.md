# Grafana operations dashboard

The main dashboard should be an operations cockpit, not a collection of
database tables. Use the queries in `docs/grafana-monitoring-queries.sql`, but
present them with the layout below.

## Main screen

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ SYSTEM HEALTH: HEALTHY / ATTENTION REQUIRED / CRITICAL                     │
└─────────────────────────────────────────────────────────────────────────────┘
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌─────────────────────┐
│ Last refresh  │ │ Failed runs   │ │ SLA breached  │ │ Notifications failed│
│ 12 min ago    │ │      0        │ │      8        │ │          0          │
└───────────────┘ └───────────────┘ └───────────────┘ └─────────────────────┘
┌──────────────────────────────────┐ ┌────────────────────────────────────────┐
│ Pipeline health — 24 hours       │ │ SLA risk by team                       │
│ Time series                      │ │ Horizontal bar chart                    │
└──────────────────────────────────┘ └────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────────┐
│ WHAT NEEDS ACTION NOW — one prioritized table                              │
└─────────────────────────────────────────────────────────────────────────────┘
▸ Diagnostics and ticket details (collapsed)
```

Use these visualizations:

- `System health banner`: Stat, transparent background, full width.
- `Last refresh`, `Failed runs`, `SLA breached`, `Notifications failed`:
  four compact Stat panels.
- `Pipeline health`: Time series with loaded and rejected rows.
- `SLA risk by team`: Horizontal bar chart, stacked by breached and nearing SLA.
- `What needs action now`: Table. Hide it entirely when there are no issues.
- `Diagnostics and ticket details`: collapsed row containing the detailed
  pipeline, rejection, notification, and ticket tables.

This gives managers the answer in five seconds while keeping technical evidence
one click away.

## Colours and thresholds

Use one consistent status language:

- Green `#299c46`: healthy / zero failures.
- Amber `#e5ac0e`: warning / nearing SLA / delayed.
- Red `#d44a3a`: critical / breached / failed.
- Grey `#8e8e8e`: no data or not applicable.

Avoid pie charts, gauges, and rainbow colours. Use red only when somebody must
act. Keep panel titles short and put explanations in panel descriptions.

Set dashboard refresh to one minute and default the time range to the last 24
hours. The supplied freshness thresholds assume a 30-minute pipeline schedule.

## Alerting

Create these alerts:

- Pipeline freshness is `CRITICAL` for five minutes.
- Latest pipeline run is `CRITICAL`.
- Pipeline failures have a value above zero.
- Report email or task reminder delivery is `CRITICAL`.
- Breached items are above zero, grouped by division and assignee group.

## Database access

Use a dedicated read-only PostgreSQL login for Grafana:

```sql
CREATE ROLE grafana_reader LOGIN PASSWORD '<store-in-your-secret-manager>';
GRANT CONNECT ON DATABASE itil_reports TO grafana_reader;
GRANT USAGE ON SCHEMA staging, reporting, config TO grafana_reader;
GRANT SELECT ON
    staging.elt_run_log,
    staging.elt_rejected_records,
    reporting.pipeline_heartbeat,
    reporting.daily_report_records,
    reporting.report_email_deliveries,
    reporting.task_reminder_executions,
    config.report_email_subscriptions,
    config.task_reminder_subscriptions
TO grafana_reader;
ALTER ROLE grafana_reader SET statement_timeout = '10s';
ALTER ROLE grafana_reader SET default_transaction_read_only = on;
```

Replace the example password before running the role script. Do not grant
Grafana broad access to `config.users`, `config.user_sessions`,
`staging.raw_changes.raw_payload`, or recipient lists.

The default freshness thresholds assume the supplied cron runs every 30
minutes. If production uses another interval, set warning to schedule plus
five minutes and critical to schedule plus fifteen minutes.
