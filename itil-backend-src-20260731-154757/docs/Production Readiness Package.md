# ITIL Group Reports Backend - Production Infrastructure Readiness

**Document reference:** MOP-ITIL-REP-001
**Target environment:** Production
**Application:** ITIL Group Reports Automation - Backend and Database
**Purpose:** Infrastructure preparation and readiness confirmation before backend deployment

## 1. Scope

The production server and compute capacity have already been agreed and are not
part of this document.

This document requests only the host preparation, storage, access, network, and
runtime prerequisites required before the application team deploys the release.

This backend deployment consists of:

- A FastAPI/Python application container, including the reporting pipeline and dbt.
- A PostgreSQL 16 container.
- Persistent host storage for PostgreSQL data, application data, output, and logs.

Production should mirror the proven QA container names, directory layout, and
shared rootless Podman network as closely as possible. Infrastructure prepares
the host; the application team owns application release deployment.

The frontend, Nginx, DNS, TLS, host port `3001`, frontend environment variables,
and frontend rollback are covered separately by **MOP-ITIL-FE-001**. This
document retains only the shared integration contract: the frontend reaches the
backend at `http://itil-backend-api:8000` on the rootless Podman network
`itil-net`.

## 2. Infrastructure Actions Required

### 2.1 Runtime and host utilities

Please install or confirm the following on the production Linux host:

- Podman 4.x or later.
- A Compose implementation compatible with `docker-compose.yml`
  (`podman compose` or `podman-compose`).
- `bash` 4 or later, `curl`, `tar`, `gzip`, `unzip`, and `ca-certificates`.
- `cron`/`cronie`, with the daemon enabled.
- Time synchronisation enabled and the host timezone set to
  `Africa/Johannesburg`.

Python, dbt, and PostgreSQL do not need to be installed directly on the host;
they are supplied by the application containers.

The deployment requires the following container images. Please provide approved
registry access or arrange for the images to be preloaded:

```text
python:3.12-slim
postgres:16-alpine
```

### 2.2 Service account and access

Please provide:

- A dedicated production service account, preferably `svc_itil_reports`.
- Rootless Podman configuration for that account, including subordinate UID/GID
  mappings where required.
- User lingering enabled for that account so rootless containers survive logout
  and can return after a host restart.
- Ownership of the application paths listed below.
- SSH access from the approved deployment/admin workstation to TCP `22`.
- Permission to manage the application's containers and crontab.
- Limited sudo access only where required to manage the cron service or approved
  system services.

The personal account `mdles002` should not be used as the long-term production
runtime identity unless Infrastructure has explicitly approved it.

### 2.3 Persistent directories

Please create the following directory structure:

```bash
sudo mkdir -p /opt/itil-report-stack/{releases,shared,scripts}
sudo mkdir -p /opt/itil-report-stack/shared/{pgdata,backups,data,output,logs/dbt,dbt/target}
sudo chown -R svc_itil_reports:svc_itil_reports /opt/itil-report-stack
sudo chmod 750 /opt/itil-report-stack
```

The following paths must persist across deployments:

```text
/opt/itil-report-stack/shared/.env
/opt/itil-report-stack/shared/pgdata/
/opt/itil-report-stack/shared/backups/
/opt/itil-report-stack/shared/data/
/opt/itil-report-stack/shared/output/
/opt/itil-report-stack/shared/logs/
/opt/itil-report-stack/shared/dbt/target/
```

This is the first production deployment. The backup and rollback controls that
exist in QA are not yet present in production. Production backup storage,
scheduling, retention, and rollback capability must therefore be created before
go-live.

No new CPU/RAM/server sizing approval is requested by this document.

### 2.4 Network and firewall rules

| Direction     | Port/protocol                     | Source or destination                 | Purpose                              |
| ------------- | --------------------------------- | ------------------------------------- | ------------------------------------ |
| Inbound       | TCP`22`                         | Approved deployment/admin workstation | Deployment and administration        |
| Internal only | TCP`8000`                       | Frontend container on`itil-net`     | FastAPI backend                      |
| Internal only | TCP`5432`                       | Backend container on`itil-net`      | PostgreSQL; do not expose externally |
| Outbound      | TCP`443` or approved Helix port | Approved BMC Helix endpoint/proxy     | Report data extraction               |
| Outbound      | TCP`25` or `587`              | Approved internal SMTP relay          | Report and reminder email delivery   |
| Outbound      | TCP`443`                        | Approved container registry           | Image pull/build dependencies        |

Notes:

- TCP `8000` and `5432` must not be exposed to user networks.
- The frontend must use `http://itil-backend-api:8000` as its internal backend
  origin on `itil-net`; it must not use the public frontend hostname.

The backend `docker-compose.yml` joins the external `itil-net` network
(create it once with `podman network create itil-net`) and publishes TCP `8000`
and PostgreSQL (host port `5433`) on `127.0.0.1` only. Infrastructure should
verify the resulting host listeners and firewall state before go-live.

Please complete the following values and return them to the application team:

| Production item                           | Value                                     |
| ----------------------------------------- | ----------------------------------------- |
| Linux hostname                            | ______________________________            |
| Server IP                                 | ______________________________            |
| Rootless service account                  | `svc_itil_reports` / __________________ |
| Approved deployment source/workstation    | ______________________________            |
| Registry or offline image-transfer method | ______________________________            |
| Monitoring/alert destination              | ______________________________            |

### 2.5 Protected production configuration

Please create or permit the application team to create:

```text
/opt/itil-report-stack/shared/.env
```

Set ownership to the production service account and permissions to `600`.
Secrets must be supplied through the approved secret-management process and
must not be included in email or committed to source control.

Use the following production template. Values in angle brackets must be supplied
through the approved production process.

```env
# Runtime, logging, and pipeline
ENVIRONMENT=production
WORKSPACE_TIMEZONE=Africa/Johannesburg
RUNTIME_SCHEMA_BOOTSTRAP_ENABLED=false
API_WORKERS=1
EXCEL_DROP_DIR=/app/data/excel_drop
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_MAX_SIZE=20m
LOG_MAX_FILES=5
PIPELINE_WEEKDAYS_ONLY=false
PIPELINE_SCHEDULE_HOUR=7
TEST_DATA_CLEANUP_ENABLED=false

# API and authentication
API_HOST=0.0.0.0
API_PORT=8000
API_CORS_ORIGINS=<approved-production-frontend-origin>
JWT_SECRET=<new-long-random-production-secret>
SUPER_ADMIN_EMAIL=<approved-production-super-admin-email>
SUPER_ADMIN_INITIAL_PASSWORD=<temporary-production-admin-password>
AUTH_ALLOWED_EMAIL_DOMAINS=vodacom.co.za,vodacom.com,vcontractor.co.za
REQUIRE_DB_ON_STARTUP=true

# Bundled PostgreSQL container
POSTGRES_DB=postgres
POSTGRES_USER=itil_admin
POSTGRES_PASSWORD=<production-database-password>
DB_CONNECT_TIMEOUT=5
DB_CONNECT_RETRIES=3
DB_RETRY_DELAY_SECONDS=2
DBT_RUN_RETRIES=2
DBT_RETRY_DELAY_SECONDS=5

# BMC Helix
HELIX_BASE_URL=https://vodacom-restapi.onbmc.com
HELIX_USERNAME=<approved-production-helix-service-account>
HELIX_PASSWORD=<production-helix-password>
HELIX_VERIFY_SSL=true
HELIX_PROXY_URL=
HELIX_PAGE_SIZE=1000
HELIX_MAX_RECORDS=50000
HELIX_DATE_FIELD=Create Date
HELIX_ENRICH_CHANGE_SCHEDULES=true
HELIX_CHANGE_LOOKUP_BATCH_SIZE=50
HELIX_INCLUDE_YESTERDAY_SUCCESS_CLOSURES=true
HELIX_USE_INCREMENTAL_WATERMARK=false
HELIX_PERIOD=

# Daily Report email delivery
MAIL_PROVIDER=smtp
MAIL_FROM_ADDRESS=INTSS.ServiceDelivery@vodacom.co.za
MAIL_FROM_NAME=ITIL Daily Reports
REPORT_EMAIL_RETRY_MINUTES=15
REPORT_EMAIL_MAX_ATTEMPTS=5
REPORT_EMAIL_AUTOMATION_APPROVED=false
REPORT_EMAIL_SCHEDULER_ENABLED=true
REPORT_EMAIL_SCHEDULER_INTERVAL_SECONDS=60
REPORT_EMAIL_WEEKDAYS_ONLY=true
REPORT_EMAIL_MANUAL_SEND_ENABLED=false
REPORT_EMAIL_ALLOW_EXTERNAL=false
REPORT_EMAIL_ALLOWED_DOMAINS=vodacom.co.za,vodacom.com,vcontractor.co.za
SMTP_HOST=<approved-production-smtp-relay>
SMTP_PORT=25
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=false
SMTP_TIMEOUT_SECONDS=30

# Outstanding-task reminders
TASK_REMINDER_AUTOMATION_KEY=
TASK_REMINDER_STALE_DAYS=7
TASK_REMINDER_AUTOMATION_APPROVED=false
TASK_REMINDER_SCHEDULER_ENABLED=true
TASK_REMINDER_SCHEDULER_INTERVAL_SECONDS=60
TASK_REMINDER_WEEKDAYS_ONLY=true
```

For the bundled PostgreSQL container, do not copy the local-development
`DATABASE_URL` from `.env.example`. `docker-compose.yml` constructs the internal
container URL from `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`.
`DATABASE_URL`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`
are needed only if the approved design changes to an external PostgreSQL
service.

Optional Helix tuning values such as `HELIX_GROUPS`, `HELIX_STATUSES`,
`HELIX_BATCH_SIZE`, `HELIX_REQUEST_SLEEP_SECONDS`, `HELIX_USE_FIELD_SELECTION`,
`HELIX_HTTP_PROXY`, and `HELIX_HTTPS_PROXY` should be added only when the
production Helix/network design requires overrides.

The two automation approval flags intentionally remain `false` until business
and operational approval is confirmed. The schedulers may run while approval is
off, but they will not send automated emails.

The following values must not be copied from QA and must be finalised for
production:

- `API_CORS_ORIGINS` - use the final production frontend URL(s), with no
  `localhost` or QA IP addresses.
- `JWT_SECRET` - generate a new long random production secret.
- `SUPER_ADMIN_INITIAL_PASSWORD` - use a new temporary production password and
  rotate it after first login.
- `POSTGRES_PASSWORD` - use a new production database password.
- `HELIX_USERNAME` and `HELIX_PASSWORD` - confirm the approved production Helix
  service account.
- `HELIX_PROXY_URL` - set only if the production network requires it.
- Email and reminder approval flags - enable only after the production approvals
  and send tests are complete.

`API_SECRET_KEY` from QA is not an application setting and must not be used as a
replacement for `JWT_SECRET`. Duplicate variables from the QA file should be
written only once in the production file. `TEST_DATA_CLEANUP_ENABLED` must remain
`false` in production.

### 2.6 Backup and rollback preparation

Infrastructure must prepare the following production controls before go-live:

- A protected backup location at
  `/opt/itil-report-stack/shared/backups/`, owned by the production service
  account and not accessible to ordinary users.
- Sufficient storage for the agreed retention period.
- An automated PostgreSQL logical backup using `pg_dump`.
- A daily backup schedule under the production service account.
- A documented retention and cleanup schedule.
- Monitoring or alerting for failed backups.
- A non-destructive restore test into an isolated test database/container during
  the production deployment/change window.
- Release directories and a `current` symlink so the application can be rolled
  back to the previous approved release.
- Retention of the first verified production release as the rollback baseline
  for later deployments.

Recommended daily database-backup command:

```bash
mkdir -p /opt/itil-report-stack/shared/backups
podman exec itil-postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "/opt/itil-report-stack/shared/backups/itil-reports-$(date +%Y%m%d-%H%M).sql.gz"
```

The final backup time and retention period must follow the approved production
operations standard. A backup must also run immediately before every application
upgrade or database schema change.

Database restore procedure. The target database must be empty or prepared under
the approved restore runbook; do not run this example against the active
production database as a test:

```bash
gunzip -c /opt/itil-report-stack/shared/backups/<approved-backup>.sql.gz \
  | podman exec -i itil-postgres psql \
      -U <production-database-user> \
      -d <production-database-name>
```

Application rollback procedure:

```bash
ln -sfn /opt/itil-report-stack/releases/<previous-release> \
  /opt/itil-report-stack/current

cd /opt/itil-report-stack/current
podman-compose up -d --build
curl --fail http://127.0.0.1:8000/api/v1/health
```

The exact Compose command must match the implementation installed by
Infrastructure (`podman compose` or `podman-compose`). Database restore must be
performed only when required and under the approved production change process.
An application rollback does not automatically require a database restore.
For the first production deployment there is no previous production release.
The initial rollback is to stop the new backend and database containers and
restore data only if the approved change introduced data that must be reversed.
After the first release is accepted, retain it as the baseline for subsequent
backend rollbacks.

## 3. Application-Team Deployment and Validation

After Infrastructure confirms readiness, the application team will:

1. Transfer the approved release to
   `/opt/itil-report-stack/releases/<release-tag>`.
2. Start the PostgreSQL and application containers.
3. Initialise the database schema and dbt reporting models.
4. Run the first Helix pipeline load.
5. Validate the health endpoint.
6. Configure the approved pipeline and production backup schedules.
7. Test database restore and application rollback under the approved change.

Validation commands will be run under the production service account:

```bash
podman --version
podman ps
podman exec itil-backend-api bash deploy/init-db.sh
podman exec itil-backend-api bash deploy/run-pipeline.sh
podman exec itil-backend-api python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').read()"
```

Expected health response:

```json
{
  "status": "ok"
}
```

Application deployment, database initialisation, enabling email automation, and
the first production data load remain application-team/change-window activities.

## 4. Infrastructure Readiness Confirmation

Please confirm the following before the deployment session:

- [ ] Production hostname and IP address.
- [ ] Production service account and SSH access.
- [ ] Podman and a compatible Compose implementation installed.
- [ ] Rootless Podman confirmed and user lingering enabled for the service account.
- [ ] Cron service and time synchronisation enabled.
- [ ] Persistent application directories created with correct ownership.
- [ ] Registry access approved or both backend base images preloaded.
- [ ] Helix endpoint/proxy connectivity approved.
- [ ] SMTP relay connectivity and sender address approved.
- [ ] Production frontend origin supplied for backend CORS configuration.
- [ ] External access to TCP `8000` and `5432` is blocked.
- [ ] Shared rootless Podman network `itil-net` can be created by the service account.
- [ ] Production backup directory and permissions created.
- [ ] Automated database backup schedule and retention configured.
- [ ] Backup failure monitoring/alerting configured.
- [ ] Database restore procedure tested successfully using an isolated target.
- [ ] Release directories and application rollback procedure prepared.
- [ ] First verified production release will be retained as the rollback baseline.
- [ ] Approved Helix service account details available through the secure process.
- [ ] Approved Super Admin email available.

## 5. Suggested Email

**Subject:** ITIL Group Reports Backend - Production Infrastructure Readiness Request

Hi Kwanele and Team,

Please find attached the production infrastructure readiness document for the
ITIL Group Reports backend and database.

The production server and compute capacity have already been agreed, so this
document does not request or revisit server sizing. It covers only the remaining
backend host preparation, rootless Podman runtime, persistent directories,
service account, internal network access, backup/rollback, and secure
configuration prerequisites. Frontend and Nginx readiness are covered separately
by MOP-ITIL-FE-001.

Please review Section 4 and confirm readiness for the production deployment
session. Once confirmed, the application team will deploy the approved release,
initialise the database and reporting models, run the first pipeline load, and
validate the health endpoint.

Regards,
Siphamandla
