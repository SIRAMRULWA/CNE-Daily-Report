# Container Deployment

Use this for a controlled manual deployment. Automated deployments use
`deploy-backend.ps1`, but both workflows use the same release and shared-data
layout.

For the authoritative production infrastructure contract, see
`docs/Production Readiness Package.md`. The Docker-oriented operating
procedure remains in `docs/production-server-mop.md`.

## Server prerequisites

- Docker Engine with the Compose plugin
- Port `8000` open to the users or reverse proxy that will call the API
- Enough disk for `/opt/itil-report-stack/shared`, including PostgreSQL data
  and archived input files

## First deployment

1. From Windows, create a clean deployment ZIP:

   ```powershell
   .\deploy\package-release.ps1
   ```

2. Copy and extract the ZIP into a versioned release, then update `current`:

   ```bash
   mkdir -p /opt/itil-report-stack/releases/<version>
   unzip /path/to/itil-group-reports-<version>.zip \
     -d /opt/itil-report-stack/releases/<version>
   ln -sfn /opt/itil-report-stack/releases/<version> \
     /opt/itil-report-stack/current
   ```

3. Create the persistent runtime folders expected by Compose:

   ```bash
   mkdir -p /opt/itil-report-stack/shared/{pgdata,backups,data,output,logs/dbt,dbt/target}
   cd /opt/itil-report-stack/current
   ```

4. Create `.env` from `.env.example` and set the QA values:

   ```bash
   cp .env.example /opt/itil-report-stack/shared/.env
   chmod 600 /opt/itil-report-stack/shared/.env
   nano /opt/itil-report-stack/shared/.env
   ```

   Minimum values to change:

   ```bash
   ENVIRONMENT=qa
   RUNTIME_SCHEMA_BOOTSTRAP_ENABLED=false
   API_WORKERS=1
   POSTGRES_PASSWORD=<strong database password>
   JWT_SECRET=<long random secret>
   SUPER_ADMIN_EMAIL=<your super admin email>
   SUPER_ADMIN_INITIAL_PASSWORD=<temporary strong password>
   REQUIRE_DB_ON_STARTUP=true
   API_CORS_ORIGINS=http://your-qa-host:8000
   ```

5. Build and start:

   ```bash
   docker compose up -d --build
   ```

6. Create/upgrade the database schema and dbt reporting objects:

   ```bash
   docker compose exec app bash deploy/init-db.sh
   ```

7. Check health:

   ```bash
   curl http://localhost:8000/api/v1/health
   ```

## Running the pipeline

For Helix ingestion:

```bash
docker compose exec app bash deploy/run-pipeline.sh
```

For file ingestion, place CSV/XLSX files in `data/excel_drop`, then run:

```bash
docker compose exec -e PIPELINE_SOURCE=file app bash deploy/run-pipeline.sh
```

To schedule Helix refreshes, copy `deploy/crontab.example`, edit the project path and timing, then install it with `crontab`.

## Updating the app manually

1. Stop the app without deleting shared PostgreSQL data:

   ```bash
   docker compose down
   ```

2. Extract the new version under `/opt/itil-report-stack/releases` and update
   the `current` symlink. Keep everything under
   `/opt/itil-report-stack/shared`.
3. Rebuild and start:

   ```bash
   docker compose up -d --build
   docker compose exec app bash deploy/init-db.sh
   ```

## Backup

Before major changes:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup-itil-reports.sql
```
