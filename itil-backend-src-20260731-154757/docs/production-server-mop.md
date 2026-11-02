# Production Server Installation MOP / SOP

This is the Docker-oriented operating procedure. The authoritative production
infrastructure and shared-network requirements are defined in
`docs/Production Readiness Package.md`. Both documents use the same
`/opt/itil-report-stack` release and persistent-data layout.

## 1. Purpose

This Method of Procedure defines the software, packages, dependencies, and installation steps required to prepare a production Linux server for the ITIL Group Reports Automation solution.

The current recommended production deployment is Docker based:

- One application container for FastAPI, Python pipeline, dbt, and Helix integration.
- One PostgreSQL container using `postgres:16-alpine`.
- Bind-mounted persistent paths for PostgreSQL data, application data, output,
  dbt logs, and dbt target artifacts.

## 2. Mail-Ready Response

Hi Kwanele,

Thank you for confirming that the production server has been cleaned up and is ready.

Please find the attached MOP/SOP for the ITIL Group Reports production environment preparation. The server requires Docker Engine, Docker Compose plugin, PostgreSQL through the supplied Docker Compose stack, standard Linux utilities, persistent storage, firewall access to the API port or reverse proxy, and outbound access to the Helix API/proxy endpoint.

Once the listed prerequisites are installed, we can schedule a session to validate Docker, deploy the release package, configure the production `.env`, initialize the database/dbt models, run the first pipeline load, and confirm `/api/v1/health`.

Regards,  
Siphamandla

## 3. Scope

In scope:

- Production server prerequisites.
- Required operating system packages.
- Docker and Docker Compose installation.
- Application deployment using this repository.
- PostgreSQL container preparation.
- Database/dbt initialization.
- Pipeline scheduling.
- Health checks, backup, and rollback.

Out of scope:

- Provisioning the Linux virtual machine.
- Firewall approval outside the server.
- DNS, TLS certificate procurement, and load balancer change approvals.
- Helix credential ownership.
- Frontend deployment, unless the frontend is separately packaged and deployed on the same host.

## 4. Server Requirements

Minimum recommended server profile:

| Item | Recommendation |
| --- | --- |
| OS | 64-bit Linux, Ubuntu 22.04/24.04 LTS or RHEL/Rocky 8/9 |
| CPU | 2 vCPU minimum, 4 vCPU recommended |
| Memory | 4 GB minimum, 8 GB recommended |
| Disk | 50 GB minimum, more if report history/input archives are retained |
| Network | Inbound API/reverse-proxy port, outbound Helix/proxy access |
| Time | NTP/time sync enabled |

Required inbound access:

| Port | Purpose | Notes |
| --- | --- | --- |
| `8000` | FastAPI application | Can be exposed directly or behind Nginx/Apache/F5 |
| `80` / `443` | Optional reverse proxy | Recommended for user-facing production access |

Required outbound access:

| Destination | Purpose |
| --- | --- |
| Docker registry or internal image registry | Pull `python:3.12-slim` and `postgres:16-alpine` if images are not preloaded |
| Helix API base URL | Production/QA Helix extraction |
| Helix proxy URL, if required | Network proxy for Helix API |

## 5. Required Software

Install on the Linux host:

| Software | Required | Purpose |
| --- | --- | --- |
| Docker Engine | Yes | Runs app and PostgreSQL containers |
| Docker Compose plugin v2 | Yes | Runs `docker compose` deployment |
| `curl` | Yes | Health checks |
| `tar` / `unzip` | Yes | Release package extraction |
| `cron` / `cronie` | Yes | Scheduled pipeline refresh |
| `ca-certificates` | Yes | HTTPS certificate trust |
| `openssl` | Recommended | Generate secure secrets |
| `nano` or `vim` | Recommended | Edit `.env` |
| Nginx or Apache | Optional | Reverse proxy and TLS termination |
| PostgreSQL client tools | Optional | Manual DB inspection/backup outside Docker |

Do not install Python, dbt, or application Python packages directly on the host for the Docker deployment. The Docker image installs those from `requirements.txt`.

Do not install PostgreSQL directly on the host unless the architecture is changed to use an external database. The supplied `docker-compose.yml` runs PostgreSQL in Docker.

## 6. Docker Installation

### Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg unzip tar cron openssl

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" |
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

### RHEL / Rocky / AlmaLinux

```bash
sudo dnf install -y dnf-plugins-core curl unzip tar cronie openssl ca-certificates
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo systemctl enable --now crond
```

### Verify Docker

```bash
docker --version
docker compose version
sudo systemctl status docker --no-pager
```

Expected:

- Docker Engine returns a version.
- `docker compose version` returns Compose v2.
- Docker service is active.

## 7. Docker Images

The deployment needs these base images:

```text
python:3.12-slim
postgres:16-alpine
```

If the production server has internet or approved registry access, Docker pulls these during build/start.

If the production server has no registry access, preload the images:

```bash
docker load -i python-3.12-slim.tar
docker load -i postgres-16-alpine.tar
```

Confirm:

```bash
docker images | grep -E 'python|postgres'
```

## 8. Release Package Preparation

On the Windows build/admin machine:

```powershell
.\deploy\package-release.ps1
```

This creates:

```text
dist/itil-group-reports-<version>.zip
```

Transfer the ZIP to the production server using the approved method, for example SCP, SFTP, or a controlled file share.

## 9. Server Directory Setup

On the production server, create the release and persistent paths used by
`docker-compose.yml` and `deploy-backend.ps1`:

```bash
sudo mkdir -p /opt/itil-report-stack/{releases,shared,scripts}
sudo mkdir -p /opt/itil-report-stack/shared/{pgdata,backups,data,output,logs/dbt,dbt/target}
sudo chown -R "$USER":"$USER" /opt/itil-report-stack
mkdir -p /opt/itil-report-stack/releases/<version>
unzip /path/to/itil-group-reports-<version>.zip \
  -d /opt/itil-report-stack/releases/<version>
ln -sfn /opt/itil-report-stack/releases/<version> \
  /opt/itil-report-stack/current
cd /opt/itil-report-stack/current
chmod +x deploy/*.sh
```

Keep these paths persistent across application updates:

```text
/opt/itil-report-stack/shared/.env
/opt/itil-report-stack/shared/pgdata/
/opt/itil-report-stack/shared/backups/
/opt/itil-report-stack/shared/data/
/opt/itil-report-stack/shared/output/
/opt/itil-report-stack/shared/logs/
/opt/itil-report-stack/shared/dbt/target/
```

## 10. Environment Configuration

Create the production `.env` at the path mounted by Compose:

```bash
cp .env.example /opt/itil-report-stack/shared/.env
chmod 600 /opt/itil-report-stack/shared/.env
nano /opt/itil-report-stack/shared/.env
```

Set production values. Do not use sample passwords from `.env.example`.

Minimum required values:

```bash
ENVIRONMENT=production
WORKSPACE_TIMEZONE=Africa/Johannesburg
RUNTIME_SCHEMA_BOOTSTRAP_ENABLED=false
API_WORKERS=1
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_MAX_SIZE=20m
LOG_MAX_FILES=5
API_PORT=8000
API_CORS_ORIGINS=https://<production-frontend-or-hostname>

POSTGRES_DB=itil_reports
POSTGRES_USER=itil_user
POSTGRES_PASSWORD=<strong-production-db-password>

JWT_SECRET=<long-random-secret>
SUPER_ADMIN_EMAIL=<approved-super-admin-email>
SUPER_ADMIN_INITIAL_PASSWORD=<temporary-strong-password>
AUTH_ALLOWED_EMAIL_DOMAINS=vodacom.co.za,vodacom.com,vcontractor.co.za
REQUIRE_DB_ON_STARTUP=true

HELIX_BASE_URL=<approved-helix-base-url>
HELIX_USERNAME=<helix-service-account>
HELIX_PASSWORD=<helix-service-account-password>
HELIX_VERIFY_SSL=true
HELIX_PROXY_URL=<proxy-url-if-required>
HELIX_PAGE_SIZE=1000
HELIX_MAX_RECORDS=50000
HELIX_USE_INCREMENTAL_WATERMARK=false

MAIL_PROVIDER=smtp
MAIL_FROM_ADDRESS=<approved-sender-address>
SMTP_HOST=<approved-smtp-relay>
TASK_REMINDER_AUTOMATION_KEY=<long-random-integration-secret>
TASK_REMINDER_STALE_DAYS=7
TASK_REMINDER_AUTOMATION_APPROVED=false
TASK_REMINDER_SCHEDULER_ENABLED=true
TASK_REMINDER_SCHEDULER_INTERVAL_SECONDS=60
TASK_REMINDER_WEEKDAYS_ONLY=true
```

Generate a strong JWT secret:

```bash
openssl rand -hex 32
```

If the optional external automation trigger is approved, generate an independent
automation key and store it only in the protected backend environment and the
approved automation-platform secret store:

```bash
openssl rand -hex 32
```

Important:

- `DATABASE_URL` takes precedence over `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.
- For the supplied Docker Compose deployment, `docker-compose.yml` sets `DATABASE_URL` to the bundled PostgreSQL service.
- If production uses an external PostgreSQL service instead, set `DATABASE_URL` explicitly and adjust the Compose file intentionally.

## 11. Build And Start

From `/opt/itil-report-stack/current`:

```bash
docker compose up -d --build
docker compose ps
```

Expected:

- `postgres` is healthy.
- `app` is running.

View logs:

```bash
docker compose logs -f app
docker compose logs -f postgres
```

Application logs are one-line JSON in production. Every API response includes an
`X-Request-ID`; use that value to find the matching request and error:

```bash
docker compose logs app | grep '<request-id>'
```

The request log includes the HTTP method, path, status, duration, authenticated
actor, role, session ID, client IP, and result. Docker rotates each service's
logs according to `LOG_MAX_SIZE` and `LOG_MAX_FILES` so logs cannot grow without
limit. Business audit history remains in `config.activity_log`; login attempts
remain in `config.login_history`; pipeline outcomes remain in
`staging.elt_run_log`. These database records survive container recreation
through the PostgreSQL volume.

## 12. Initialize Database And dbt Models

Run once after first start and after each release:

```bash
docker compose exec app bash deploy/init-db.sh
```

This performs:

- Database connectivity check.
- Versioned schema upgrades through `app_core.migrations`, recorded in
  `config.schema_migrations`.
- dbt model run, including reporting marts.

The API container also applies or verifies these migrations before Uvicorn
starts. This ensures a new production database is initialized before strict
authentication bootstrap runs.

Expected final line:

```text
Database schema and dbt models are ready.
```

## 13. First Health Check

```bash
curl http://localhost:8000/api/v1/health
```

Expected:

```json
{
  "status": "ok"
}
```

If the API is behind a reverse proxy, also test the production URL:

```bash
curl https://<production-hostname>/api/v1/health
```

## 14. First Pipeline Run

For Helix ingestion:

```bash
docker compose exec app bash deploy/run-pipeline.sh
```

For file ingestion:

```bash
cp <input-file>.xlsx data/excel_drop/
docker compose exec -e PIPELINE_SOURCE=file app bash deploy/run-pipeline.sh
```

Check health again after the run:

```bash
curl http://localhost:8000/api/v1/health
```

## 15. Schedule Pipeline Refresh

Review `deploy/crontab.example`, update the path and timing, then install:

```bash
cp deploy/crontab.example deploy/crontab.production
nano deploy/crontab.production
crontab deploy/crontab.production
crontab -l
```

Default example:

```text
*/30 * * * * cd /opt/itil-report-stack/current && /usr/bin/docker compose exec -T app bash deploy/run-pipeline.sh >> /opt/itil-report-stack/shared/logs/pipeline-cron.log 2>&1
```

Confirm the log file after the scheduled time:

```bash
tail -100 /opt/itil-report-stack/shared/logs/pipeline-cron.log
```

## 16. Optional Reverse Proxy

If production should expose HTTPS on port `443`, place Nginx, Apache, F5, or another approved proxy in front of the API.

Proxy target:

```text
http://127.0.0.1:8000
```

Minimum headers:

```text
Host
X-Forwarded-For
X-Forwarded-Proto
```

Set `API_CORS_ORIGINS` to the final frontend origin, for example:

```bash
API_CORS_ORIGINS=https://itil-reports.example.co.za
```

## 17. Backup Procedure

Before upgrades or major changes:

```bash
cd /opt/itil-report-stack/current
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "/opt/itil-report-stack/shared/backups/backup-itil-reports-$(date +%Y%m%d-%H%M).sql"
```

Also preserve:

```text
/opt/itil-report-stack/shared/.env
/opt/itil-report-stack/shared/data/
/opt/itil-report-stack/shared/output/
/opt/itil-report-stack/shared/logs/
/opt/itil-report-stack/shared/dbt/target/
```

## 18. Upgrade Procedure

1. Create a backup.
2. Stop containers without deleting the PostgreSQL volume:

   ```bash
   docker compose down
   ```

3. Extract the new package into a new `/opt/itil-report-stack/releases/<version>`
   directory and update the `current` symlink.
4. Preserve everything under `/opt/itil-report-stack/shared`.
5. Start and initialize:

   ```bash
   docker compose up -d --build
   docker compose exec app bash deploy/init-db.sh
   curl http://localhost:8000/api/v1/health
   ```

## 19. Rollback Procedure

1. Stop current containers:

   ```bash
   docker compose down
   ```

2. Point `/opt/itil-report-stack/current` to the previous release directory.
3. Keep the same `/opt/itil-report-stack/shared` configuration and PostgreSQL
   data. Database migrations are forward-only; restore a database backup only
   through an approved rollback plan.
4. Start:

   ```bash
   docker compose up -d --build
   docker compose exec app bash deploy/init-db.sh
   curl http://localhost:8000/api/v1/health
   ```

If database rollback is required, restore from the backup SQL under change-control approval.

## 20. Validation Checklist

| Check | Command | Expected |
| --- | --- | --- |
| Docker installed | `docker --version` | Version shown |
| Compose installed | `docker compose version` | Version shown |
| Containers running | `docker compose ps` | `app` running, `postgres` healthy |
| API health | `curl http://localhost:8000/api/v1/health` | `status=ok` |
| DB/dbt initialized | `docker compose exec app bash deploy/init-db.sh` | Completes successfully |
| Pipeline run | `docker compose exec app bash deploy/run-pipeline.sh` | Completes successfully |
| Cron installed | `crontab -l` | Pipeline schedule visible |
| Logs writable | `tail logs/pipeline-cron.log` | Log entries visible after schedule |

## 21. Handover Items Required From Infrastructure

Before the deployment session, infrastructure should confirm:

- Linux OS and version.
- Server hostname and IP.
- Whether Docker registry access is allowed.
- Whether outbound Helix API/proxy access is allowed.
- Production URL/origin for `API_CORS_ORIGINS`.
- Whether the API will be exposed directly on `8000` or behind HTTPS reverse proxy.
- Backup storage location.
- Approved service account for Helix.
- Approved Super Admin email.

## 22. Notes

- The app container uses one Uvicorn worker to avoid first-boot Super Admin bootstrap races.
- `/api/v1/health` is public and should be used for basic uptime checks.
- `/api/v1/pipeline-runs` requires `SUPER_ADMIN` and is used for pipeline history.
- Historical Daily Report drill-through requires dbt to create both `reporting.daily_report_summary` and `reporting.daily_report_records`.
