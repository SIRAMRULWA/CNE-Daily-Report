# Frontend API Guide

## Contract

The only supported API base is `/api/v1`. The machine-readable contract is
available at `/api/openapi.json`, with interactive documentation at `/docs`.
All protected calls use `Authorization: Bearer <access_token>`.

Successful v1 responses include `API-Version: 1`. Errors contain `message`,
`detail`, `error_code`, `request_id`, and optional field-level `details`.

## Endpoints

### Authentication and current user

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/sessions` | Sign in and create a session |
| `DELETE` | `/api/v1/auth/sessions/current` | Sign out and revoke the current session |
| `GET` | `/api/v1/users/current` | Restore the signed-in user |
| `PATCH` | `/api/v1/users/current/password` | Change the current user's password |

Login returns `201` with `access_token`, `token_type`, `expires_at`, and `user`.
Unknown email and incorrect password both return `401`; the frontend must not
attempt to infer whether an account exists.

### User and security administration

| Method | Path | Minimum access |
|---|---|---|
| `GET` | `/api/v1/users` | SUPER_ADMIN |
| `POST` | `/api/v1/users` | SUPER_ADMIN |
| `PATCH` | `/api/v1/users/{user_id}` | SUPER_ADMIN |
| `DELETE` | `/api/v1/users/{user_id}` | SUPER_ADMIN |
| `POST` | `/api/v1/users/{user_id}/password-reset` | SUPER_ADMIN |
| `GET` | `/api/v1/login-attempts` | SUPER_ADMIN |
| `GET` | `/api/v1/sessions` | SUPER_ADMIN |
| `DELETE` | `/api/v1/sessions/{session_id}` | SUPER_ADMIN |

The user PATCH body may contain `status`, `role`, or both.

### Current operational data

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/operational-records` | Filtered current operational records |
| `GET` | `/api/v1/operational-records/summary` | Current grouped counts and freshness |

Supported record filters include `division`, `assignee_group`, `sla`,
`category`, `priority`, `search`, `include_excluded`, `limit`, and `offset`.
`NO_SCHEDULE` applies only to Changes without a scheduled end;
`NO_ASSIGN_TIME` applies to Incidents, Access tasks, and Events whose SLA clock
cannot be calculated because assignment time is missing.
When `data_available=false`, clear existing records and render the backend empty
state. Never substitute a historical Daily Report snapshot.

### Daily Report snapshots

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/daily-reports` | Complete selected-date report page contract |
| `GET` | `/api/v1/daily-reports/records` | Selected-snapshot drill-through records |

The main screen uses only `/api/v1/daily-reports`. Its query parameters are
`report_date`, `period`, `division`, `assignee_group`, `include_dates`,
`date_limit`, `include_records`, `sla`, and `category`. The response combines
the date context, filters, KPIs, summary rows, groups, optional available dates,
and optional records from one consistent snapshot.

Do not derive the displayed date from the browser clock. Use the response's
`report_date`, `date_from`, `date_to`, `data_available`, and historical flags.

### Divisions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/divisions` | List active divisions |
| `POST` | `/api/v1/divisions` | Create or reactivate a division |
| `GET` | `/api/v1/divisions/{division}/groups` | List mapped groups |
| `POST` | `/api/v1/divisions/{division}/groups` | Add or reactivate groups |
| `DELETE` | `/api/v1/divisions/{division}/groups/{assignee_group}` | Deactivate one mapping |
| `POST` | `/api/v1/division-group-seed-jobs` | Seed default mappings |

Always URL-encode `division` and `assignee_group` path values.

### Report subscriptions and deliveries

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/report-subscriptions` | List subscriptions |
| `POST` | `/api/v1/report-subscriptions` | Create a subscription |
| `PUT` | `/api/v1/report-subscriptions/{subscription_id}` | Replace a subscription |
| `PATCH` | `/api/v1/report-subscriptions/{subscription_id}` | Change its enabled state |
| `DELETE` | `/api/v1/report-subscriptions/{subscription_id}` | Soft-delete a subscription |
| `GET` | `/api/v1/report-deliveries` | List delivery history |
| `POST` | `/api/v1/report-deliveries` | Send a report now |

Manual delivery returns `201`. Treat all `2xx` responses as successful.

### Helix reports

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/helix-reports/fields` | Allowed fields and date fields |
| `GET` | `/api/v1/helix-reports/filters` | Active division/group filters |
| `POST` | `/api/v1/helix-reports` | Generate a direct Helix report |

### Outstanding task reminders

Use only the Task-named endpoints below. The earlier Ticket-named paths are not
part of the supported contract and must not remain in the frontend API client.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/task-reminder-subscriptions` | List reminder configurations |
| `POST` | `/api/v1/task-reminder-subscriptions` | Create a reminder configuration |
| `PUT` | `/api/v1/task-reminder-subscriptions/{subscription_id}` | Replace a configuration |
| `PATCH` | `/api/v1/task-reminder-subscriptions/{subscription_id}` | Change enabled state |
| `DELETE` | `/api/v1/task-reminder-subscriptions/{subscription_id}` | Soft-delete a configuration |
| `GET` | `/api/v1/task-reminder-executions` | List execution history |
| `POST` | `/api/v1/task-reminder-executions` | Send a task reminder now |

Subscription forms capture name, division,
optional assignee group, recipients, CC recipients, subject, schedule
frequency (`DAILY` or `WEEKLY`), weekday (`0` Monday through `6` Sunday), send
time, IANA timezone, maximum live records, and enabled state. Use the same
schedule-control pattern as report-email subscriptions. `weekday` is required
only for `WEEKLY`; the recommended timezone is `Africa/Johannesburg`.

The backend queries Helix live but applies the shared Daily Report
transformation before rendering. The FE must therefore describe this as the
current Daily Report open-task scope: Work Orders, PBIs, unsupported categories,
excluded statuses, unmapped groups, and all other Daily Report exclusions never
appear. The backend scheduler owns normal scheduled delivery; the browser does
not trigger due schedules.

The backend-only automation endpoint is
`POST /api/v1/automation/task-reminder-executions`. It is not called by the
browser. Never expose `TASK_REMINDER_AUTOMATION_KEY` or send
`X-Automation-Key` from frontend code. Full workflow details are in
`docs/task-reminders.md`.

### Audit, pipeline, service, and maintenance

| Method | Path | Access |
|---|---|---|
| `GET` | `/api/v1/audit-events` | SUPER_ADMIN |
| `GET` | `/api/v1/pipeline-runs` | SUPER_ADMIN |
| `GET` | `/api/v1/health` | Public |
| `POST` | `/api/v1/maintenance/data-cleanup-jobs` | SUPER_ADMIN, non-production and explicitly enabled |

## Frontend state rules

1. Keep the Bearer token in the shared API client and hydrate through
   `/api/v1/users/current`.
2. Route `PASSWORD_CHANGE_REQUIRED` users to password change without discarding
   the current token.
3. Keep live operational state separate from Daily Report snapshot state.
4. Use backend freshness metadata and never automatically select historical
   data when the current day is empty.
5. Display `message`; branch on `error_code`; show `request_id` for support.
6. Treat every `2xx` status as success.
7. Keep endpoint paths in one shared API module rather than page components.

## Verification checklist

- Type-check, lint, and build the frontend.
- Test login, logout, hydration, and required-password-change handling.
- Test READ_ONLY, USER, ADMIN, and SUPER_ADMIN authorization boundaries.
- Verify empty current-day operational data does not show cached history.
- Verify Daily Reports use the selected snapshot date for KPIs and records.
- Verify report `Send now` accepts `201` and refreshes delivery history.
- Verify task-reminder create/edit, enable/disable, `Send now`, and execution history.
- Verify no frontend copy or API path calls the feature a Ticket Reminder.
- Verify all frontend network calls begin with `/api/v1`.
