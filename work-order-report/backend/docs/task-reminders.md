# Live Daily Report Task Reminders

## Architecture and scope

Reminders are the live, action-oriented version of the Daily Report. They query
Helix at execution time, but pass every result through the shared Daily Report
transformation before division or team filtering. This guarantees the same:

- open-status, category, group, and division eligibility;
- Work Order and PBI exclusions;
- operational-category and unsupported-record exclusions;
- SLA calculation, ageing, and attention indicators.

Daily Reports continue to read immutable reporting snapshots. Reminders do not
modify those snapshots and never fall back to historical report data.

All Helix epoch timestamps are converted to `WORKSPACE_TIMEZONE` (normally
`Africa/Johannesburg`) before Hours Open and SLA status are calculated. The
same local values are used in the Excel attachment, and the email header shows
the timezone abbreviation (for example, `SAST`) so UTC and local clocks cannot
be mistaken for one another.

Both workflows call the canonical `HelixExtractor.extract_changes()` method.
They therefore share the TMS:Task query builder, field-to-`ChangeRecord`
mapping, paging, datetime parsing, batching, and authoritative parent-change
schedule enrichment. The Daily Report consumer may apply its date/watermark
window and successful-closure retrieval before loading pipeline tables. The
reminder consumer supplies the targeted groups and open statuses, has no
created-date restriction, and disables successful-closure retrieval.

This reuse does not make the reminder a pipeline run. The reminder never opens
or closes pipeline runs, changes the Helix watermark, loads operational tables,
runs dbt, or writes Daily Report snapshots. It consumes the shared canonical
records in memory and writes only its own execution/audit outcome.

```text
Admin-configured daily/weekly schedule
  -> backend reminder scheduler
  -> load enabled subscription and create occurrence idempotency key
  -> call the shared canonical Helix extract_changes() path
  -> apply the shared Daily Report transformation and exclusions
  -> filter by configured division and optional assignee group
  -> build branded HTML plus complete XLSX workbook
  -> send through the configured mail transport
  -> persist execution outcome and audit event
```

## Admin configuration API

Admin access is required.

### Role permissions

| Action | Admin | Super Admin | Manager/User/Read Only |
| --- | --- | --- | --- |
| View reminder subscriptions and history | Yes | Yes | No |
| Create reminder subscriptions | Yes | Yes | No |
| Edit reminder scope, recipients, schedule, and limits | Yes | Yes | No |
| Enable or disable scheduled reminders | Yes | Yes | No |
| Delete reminder subscriptions | Yes | Yes | No |
| Run an enabled reminder manually | Yes | Yes | No |

Deletion is audit-safe: the subscription is disabled and soft-deleted, while
its execution history is preserved.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/task-reminder-subscriptions` | List configurations |
| `POST` | `/api/v1/task-reminder-subscriptions` | Create configuration |
| `PUT` | `/api/v1/task-reminder-subscriptions/{subscription_id}` | Replace configuration |
| `PATCH` | `/api/v1/task-reminder-subscriptions/{subscription_id}` | Enable or disable |
| `DELETE` | `/api/v1/task-reminder-subscriptions/{subscription_id}` | Soft-delete |
| `GET` | `/api/v1/task-reminder-executions` | Search execution history |
| `POST` | `/api/v1/task-reminder-executions` | Run manually as an Admin |

Example subscription:

```json
{
  "name": "INTSS open-task afternoon reminder",
  "division": "INTSS",
  "assignee_group": null,
  "recipients": ["intss-operations@example.com"],
  "cc_recipients": [],
  "subject": "Action Required: Outstanding INTSS Tasks",
  "frequency": "DAILY",
  "weekday": null,
  "send_time": "13:00:00",
  "timezone": "Africa/Johannesburg",
  "max_records": 10000,
  "enabled": true
}
```

For `WEEKLY`, `weekday` is required (`0` Monday through `6` Sunday). For
`DAILY`, it must be null. Set `assignee_group` to target one team or leave it
null to include every active group mapped to the division. Recipient-domain
policy is shared with report emails.

The backend checks due schedules at `TASK_REMINDER_SCHEDULER_INTERVAL_SECONDS`
and generates one stable idempotency key per local scheduled occurrence. Enable
unattended delivery only after approval with
`TASK_REMINDER_AUTOMATION_APPROVED=true`. `TASK_REMINDER_WEEKDAYS_ONLY=true`
prevents all reminder schedules from running on weekends.

## Live data and email output

Each execution retrieves current `TMS:Task` rows for the active division/group
mappings and configured open statuses. It then calls the same transformation
used by the Daily Report. Only transformed, report-eligible records matching the
subscription scope can reach the email or workbook.

An item is highlighted when it has breached or is nearing SLA, is high/critical
priority, is unassigned, is pending, has no schedule, or is older than
`TASK_REMINDER_STALE_DAYS` (default seven days). The XLSX contains the complete
eligible reminder set, not only highlighted records, and includes Daily Report
category, SLA status, and hours-open fields.

The reminder email deliberately reuses the proven Daily Report layout and
Vodacom palette. It uses four KPI cards: **Open Tasks** in green,
**Nearing SLA** in amber, **Breached** in red, and **Oldest Task (Days)** in
blue. Oldest Task is the maximum whole-day age since the eligible task's create
date, or zero when the result set is empty. The group breakdown shows
**Group**, **Open**, **Near**, and **Breached**, using the same green, amber,
and red status palette as the Daily Report. Reminder-specific wording makes it
clear that the figures come from a current live Helix query and asks teams to
update and close the outstanding work. Closed-yesterday reporting is not shown
because a reminder is concerned only with work that is still open.

The attachment is generated by the exact same XLSX function as the morning
Daily Report. It therefore retains the familiar per-group worksheets, columns,
ordering, SLA row colours, filters, frozen header, widths, and filename pattern.
Only the data timing differs: the reminder workbook contains the current live
eligible Helix tasks rather than the morning snapshot.

## Optional external trigger

Normal scheduling is internal and needs no browser or automation-platform call.
An approved external integration may instead call
`POST /api/v1/automation/task-reminder-executions` with a protected
`X-Automation-Key`, `subscription_id`, and stable `idempotency_key`. Never expose
`TASK_REMINDER_AUTOMATION_KEY` to the frontend. Duplicate keys return the
existing execution and do not send twice.

## Persistence, monitoring, and support

Configuration is stored in `config.task_reminder_subscriptions`; every attempt
is stored in `reporting.task_reminder_executions`. History records trigger
source, status, recipients, eligible record count, attention count, provider,
provider message ID, safe failure details, requester, and timestamps. Health
output includes recent reminder failures and the last execution time.

Support procedure:

1. Search `/api/v1/task-reminder-executions` by subscription and status.
2. Correlate the HTTP `X-Request-ID` with the audit event.
3. Confirm the subscription, schedule, timezone, enabled state, and mappings.
4. Confirm Helix credentials, TLS/proxy connectivity, and current source data.
5. Confirm mail-provider configuration and recipient-domain policy.
6. Use an Admin manual run for a controlled end-to-end validation.

## Production activation

1. Run `deploy/init-db.sh` to apply the reminder schema.
2. Configure scheduler, stale-day, Helix, and mail settings.
3. Create a disabled subscription and validate its scope, schedule, recipients,
   subject, timezone, and safety limit.
4. Perform one Admin manual execution and inspect the email, XLSX, execution row,
   and audit event. Confirm Work Orders/PBIs and other Daily Report exclusions
   are absent.
5. Enable the subscription, set `TASK_REMINDER_AUTOMATION_APPROVED=true`, and
   observe one scheduled occurrence.
6. Monitor failed executions and Helix/mail availability after go-live.
