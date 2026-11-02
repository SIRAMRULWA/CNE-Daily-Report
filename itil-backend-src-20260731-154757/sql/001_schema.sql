-- =============================================================
-- ITIL Group Reports Automation — Database Schema
-- Run once: psql $DATABASE_URL -f sql/001_schema.sql
-- =============================================================

-- Schemas
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS reporting;
CREATE SCHEMA IF NOT EXISTS config;

-- =============================================================
-- CONTROL TABLES
-- =============================================================

CREATE TABLE IF NOT EXISTS staging.elt_run_log (
    run_id          BIGSERIAL PRIMARY KEY,
    pipeline_name   TEXT NOT NULL,
    source_entity   TEXT NOT NULL,
    source_file     TEXT,
    run_start       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_end         TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'RUNNING'
                    CHECK (status IN ('RUNNING','SUCCESS','FAILED','PARTIAL')),
    rows_extracted  INT DEFAULT 0,
    rows_loaded     INT DEFAULT 0,
    rows_rejected   INT DEFAULT 0,
    watermark_from  TIMESTAMPTZ,
    watermark_to    TIMESTAMPTZ,
    environment     TEXT DEFAULT 'dev',
    error_message   TEXT
);

CREATE TABLE IF NOT EXISTS staging.elt_watermarks (
    source_name  TEXT NOT NULL,
    entity_name  TEXT NOT NULL,
    watermark_to TIMESTAMPTZ NOT NULL,
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (source_name, entity_name)
);

CREATE TABLE IF NOT EXISTS staging.elt_rejected_records (
    id               BIGSERIAL PRIMARY KEY,
    run_id           BIGINT REFERENCES staging.elt_run_log(run_id),
    source_entity    TEXT,
    raw_data         JSONB,
    rejection_reason TEXT,
    rejected_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Editable division-to-assignee-group mapping used by the API and transform layer.
CREATE TABLE IF NOT EXISTS config.divisions (
    name       TEXT PRIMARY KEY,
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS config.division_groups (
    id             BIGSERIAL PRIMARY KEY,
    division       TEXT NOT NULL,
    assignee_group TEXT NOT NULL,
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted        BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by     TEXT,
    deleted_at     TIMESTAMPTZ,
    UNIQUE (division, assignee_group)
);
ALTER TABLE config.division_groups ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE config.division_groups ADD COLUMN IF NOT EXISTS deleted_by TEXT;
ALTER TABLE config.division_groups ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_division_groups_division ON config.division_groups(division);
CREATE INDEX IF NOT EXISTS idx_division_groups_active ON config.division_groups(active);

CREATE TABLE IF NOT EXISTS config.activity_log (
    id          BIGSERIAL PRIMARY KEY,
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT,
    actor       TEXT,
    details     JSONB DEFAULT '{}'::JSONB,
    ip_address  TEXT,
    user_agent  TEXT,
    browser     TEXT,
    operating_system TEXT,
    result      TEXT,
    request_id  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS ip_address TEXT;
ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS user_agent TEXT;
ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS browser TEXT;
ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS operating_system TEXT;
ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS result TEXT;
ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS request_id TEXT;

CREATE INDEX IF NOT EXISTS idx_activity_log_created_at ON config.activity_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_log_entity ON config.activity_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_request_id ON config.activity_log(request_id) WHERE request_id IS NOT NULL;

-- =============================================================
-- AUTHENTICATION / AUTHORIZATION
-- =============================================================

CREATE TABLE IF NOT EXISTS config.users (
    id                   BIGSERIAL PRIMARY KEY,
    email                TEXT NOT NULL UNIQUE,
    full_name            TEXT,
    password_hash        TEXT NOT NULL,
    role                 TEXT NOT NULL
                         CHECK (role IN ('SUPER_ADMIN','ADMIN','MANAGER','USER','READ_ONLY')),
    status               TEXT NOT NULL DEFAULT 'ACTIVE'
                         CHECK (status IN ('ACTIVE','DISABLED','LOCKED')),
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    created_by           TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at        TIMESTAMPTZ,
    disabled_by          TEXT,
    disabled_at          TIMESTAMPTZ,
    deleted              BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by           TEXT,
    deleted_at           TIMESTAMPTZ
);

ALTER TABLE config.users ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE config.users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE config.users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
ALTER TABLE config.users ADD COLUMN IF NOT EXISTS disabled_by TEXT;
ALTER TABLE config.users ADD COLUMN IF NOT EXISTS disabled_at TIMESTAMPTZ;
ALTER TABLE config.users ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE config.users ADD COLUMN IF NOT EXISTS deleted_by TEXT;
ALTER TABLE config.users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_single_super_admin
    ON config.users ((role))
    WHERE role = 'SUPER_ADMIN' AND deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_users_email ON config.users(LOWER(email));
CREATE INDEX IF NOT EXISTS idx_users_status ON config.users(status);

CREATE TABLE IF NOT EXISTS config.user_sessions (
    id               TEXT PRIMARY KEY,
    user_id          BIGINT NOT NULL REFERENCES config.users(id),
    token_jti        TEXT NOT NULL UNIQUE,
    issued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ NOT NULL,
    revoked_at       TIMESTAMPTZ,
    revoked_by       TEXT,
    ip_address       TEXT,
    user_agent       TEXT,
    browser          TEXT,
    operating_system TEXT,
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','REVOKED','EXPIRED'))
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON config.user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_status ON config.user_sessions(status);

CREATE TABLE IF NOT EXISTS config.login_history (
    id               BIGSERIAL PRIMARY KEY,
    user_id          BIGINT REFERENCES config.users(id),
    email            TEXT NOT NULL,
    login_time       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_address       TEXT,
    user_agent       TEXT,
    browser          TEXT,
    operating_system TEXT,
    status           TEXT NOT NULL CHECK (status IN ('SUCCESS','FAILED')),
    failure_reason   TEXT
);

CREATE INDEX IF NOT EXISTS idx_login_history_time ON config.login_history(login_time DESC);
CREATE INDEX IF NOT EXISTS idx_login_history_email ON config.login_history(LOWER(email));

-- =============================================================
-- RAW CHANGES (staging)
-- =============================================================

CREATE TABLE IF NOT EXISTS staging.raw_changes (
    id               BIGSERIAL PRIMARY KEY,
    run_id           BIGINT REFERENCES staging.elt_run_log(run_id),

    -- identifiers
    request_id       TEXT NOT NULL,
    task_id          TEXT NOT NULL DEFAULT '',

    -- source fields
    op_cat_tier1     TEXT,
    summary          TEXT,
    assignee         TEXT,
    priority         TEXT,
    status           TEXT,
    status_reason    TEXT,
    assignee_group   TEXT,
    notes            TEXT,

    -- timestamps
    create_date      TIMESTAMPTZ,
    assign_time      TIMESTAMPTZ,
    closed_time      TIMESTAMPTZ,
    scheduled_start  TIMESTAMPTZ,
    scheduled_end    TIMESTAMPTZ,

    -- derived (populated by pipeline transform layer)
    report_group     TEXT,
    report_category  TEXT,  -- INCIDENT / CHANGE / ACCESS / EVENT
    sla_status       TEXT,  -- WITHIN_SLA / NEARING_SLA / BREACHED / NO_SCHEDULE / NO_ASSIGN_TIME / CLOSED
    hours_open       NUMERIC(10,2),
    exclude_change   BOOLEAN DEFAULT FALSE,
    exclude_incident BOOLEAN DEFAULT FALSE,

    -- metadata
    source           TEXT DEFAULT 'excel',   -- excel | csv | helix_api
    raw_payload      JSONB,
    loaded_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (request_id, task_id)
);

-- Keep existing databases aligned when this file is re-run after schema changes.
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS run_id BIGINT REFERENCES staging.elt_run_log(run_id);
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS request_id TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS task_id TEXT DEFAULT '';
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS op_cat_tier1 TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS assignee TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS priority TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS status TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS status_reason TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS assignee_group TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS create_date TIMESTAMPTZ;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS assign_time TIMESTAMPTZ;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS closed_time TIMESTAMPTZ;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS scheduled_start TIMESTAMPTZ;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS scheduled_end TIMESTAMPTZ;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS report_group TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS report_category TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS sla_status TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS hours_open NUMERIC(10,2);
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS exclude_change BOOLEAN DEFAULT FALSE;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS exclude_incident BOOLEAN DEFAULT FALSE;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'excel';
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS raw_payload JSONB;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS loaded_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS deleted_by TEXT;
ALTER TABLE staging.raw_changes ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE staging.raw_changes DROP CONSTRAINT IF EXISTS raw_changes_source_check;
UPDATE staging.raw_changes SET source = 'excel' WHERE source = 'excel_upload';
ALTER TABLE staging.raw_changes ADD CONSTRAINT raw_changes_source_check
    CHECK (source IN ('excel', 'csv', 'helix_api'));

CREATE INDEX IF NOT EXISTS idx_raw_changes_request_id   ON staging.raw_changes(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_changes_assignee_grp  ON staging.raw_changes(assignee_group);
CREATE INDEX IF NOT EXISTS idx_raw_changes_report_group  ON staging.raw_changes(report_group);
CREATE INDEX IF NOT EXISTS idx_raw_changes_report_cat    ON staging.raw_changes(report_category);
CREATE INDEX IF NOT EXISTS idx_raw_changes_sla_status    ON staging.raw_changes(sla_status);
CREATE INDEX IF NOT EXISTS idx_raw_changes_scheduled_end ON staging.raw_changes(scheduled_end);
CREATE INDEX IF NOT EXISTS idx_raw_changes_run_id        ON staging.raw_changes(run_id);
CREATE INDEX IF NOT EXISTS idx_raw_changes_loaded_at     ON staging.raw_changes(loaded_at);

-- =============================================================
-- REPORTING TABLES
-- =============================================================

-- Singleton heartbeat row for Power BI refresh visibility
CREATE TABLE IF NOT EXISTS reporting.pipeline_heartbeat (
    id              INT PRIMARY KEY DEFAULT 1,
    last_run_at     TIMESTAMPTZ,
    last_run_status TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CHECK (id = 1)   -- enforce singleton
);
ALTER TABLE reporting.pipeline_heartbeat ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMPTZ;
ALTER TABLE reporting.pipeline_heartbeat ADD COLUMN IF NOT EXISTS last_run_status TEXT;
ALTER TABLE reporting.pipeline_heartbeat ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

INSERT INTO reporting.pipeline_heartbeat (id, last_run_at, last_run_status)
VALUES (1, NULL, 'NEVER')
ON CONFLICT (id) DO NOTHING;

-- Daily report summary (pre-aggregated historical daily snapshots)
-- Populated by dbt mart: daily_report_summary
CREATE TABLE IF NOT EXISTS reporting.daily_report_summary (
    id               BIGSERIAL PRIMARY KEY,
    report_date      DATE NOT NULL,
    report_group     TEXT NOT NULL,
    assignee_group   TEXT,
    sla_band         TEXT NOT NULL,  -- 'Total Open Calls' | 'Calls Nearing SLA' | 'Breached Calls'
    incident_count   INT DEFAULT 0,
    change_count     INT DEFAULT 0,
    access_count     INT DEFAULT 0,
    event_count      INT DEFAULT 0,
    total_count      INT DEFAULT 0,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (report_date, report_group, assignee_group, sla_band)
);

ALTER TABLE reporting.daily_report_summary ADD COLUMN IF NOT EXISTS assignee_group TEXT;

CREATE INDEX IF NOT EXISTS idx_daily_summary_date  ON reporting.daily_report_summary(report_date);
CREATE INDEX IF NOT EXISTS idx_daily_summary_group ON reporting.daily_report_summary(report_group);
CREATE INDEX IF NOT EXISTS idx_daily_summary_assignee_group ON reporting.daily_report_summary(assignee_group);

-- Automated Daily Report email subscriptions. A NULL assignee_group sends the
-- whole division; a populated assignee_group narrows delivery to that group.
CREATE TABLE IF NOT EXISTS config.report_email_subscriptions (
    id               BIGSERIAL PRIMARY KEY,
    name             TEXT NOT NULL,
    division         TEXT NOT NULL,
    assignee_group   TEXT,
    recipients       JSONB NOT NULL DEFAULT '[]'::JSONB,
    cc_recipients    JSONB NOT NULL DEFAULT '[]'::JSONB,
    frequency        TEXT NOT NULL DEFAULT 'DAILY'
                     CHECK (frequency IN ('DAILY','WEEKLY')),
    weekday          SMALLINT CHECK (weekday BETWEEN 0 AND 6),
    send_time        TIME NOT NULL DEFAULT '08:00',
    timezone         TEXT NOT NULL DEFAULT 'Africa/Johannesburg',
    attachment_format TEXT NOT NULL DEFAULT 'XLSX'
                     CHECK (attachment_format IN ('XLSX','CSV')),
    enabled          BOOLEAN NOT NULL DEFAULT FALSE,
    deleted          BOOLEAN NOT NULL DEFAULT FALSE,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE config.report_email_subscriptions ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_report_email_subscriptions_due
    ON config.report_email_subscriptions(enabled, frequency, send_time);
CREATE INDEX IF NOT EXISTS idx_report_email_subscriptions_scope
    ON config.report_email_subscriptions(division, assignee_group);

CREATE TABLE IF NOT EXISTS reporting.report_email_deliveries (
    id                BIGSERIAL PRIMARY KEY,
    subscription_id   BIGINT REFERENCES config.report_email_subscriptions(id),
    report_date       DATE NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('SENDING','SENT','FAILED','SKIPPED')),
    recipients        JSONB NOT NULL DEFAULT '[]'::JSONB,
    record_count      INT NOT NULL DEFAULT 0,
    provider          TEXT,
    provider_message_id TEXT,
    attempt_count     INT NOT NULL DEFAULT 1,
    error_message     TEXT,
    delivery_mode     TEXT NOT NULL DEFAULT 'AUTOMATIC'
                      CHECK (delivery_mode IN ('AUTOMATIC','MANUAL')),
    requested_by      TEXT,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    UNIQUE (subscription_id, report_date)
);
ALTER TABLE reporting.report_email_deliveries ALTER COLUMN subscription_id DROP NOT NULL;
ALTER TABLE reporting.report_email_deliveries ADD COLUMN IF NOT EXISTS delivery_mode TEXT NOT NULL DEFAULT 'AUTOMATIC';
ALTER TABLE reporting.report_email_deliveries ADD COLUMN IF NOT EXISTS requested_by TEXT;

CREATE INDEX IF NOT EXISTS idx_report_email_deliveries_recent
    ON reporting.report_email_deliveries(started_at DESC);

-- Real-time outstanding-task reminder configuration. Admins own the schedule;
-- the backend scheduler evaluates each enabled subscription and uses a stable
-- idempotency key for every configured occurrence.
-- Preserve configurations created before the business terminology changed
-- from "ticket" to "task".
DO $$
BEGIN
    IF to_regclass('config.task_reminder_subscriptions') IS NULL
       AND to_regclass('config.ticket_reminder_subscriptions') IS NOT NULL THEN
        ALTER TABLE config.ticket_reminder_subscriptions RENAME TO task_reminder_subscriptions;
    END IF;
    IF to_regclass('reporting.task_reminder_executions') IS NULL
       AND to_regclass('reporting.ticket_reminder_executions') IS NOT NULL THEN
        ALTER TABLE reporting.ticket_reminder_executions RENAME TO task_reminder_executions;
    END IF;
    IF to_regclass('config.idx_task_reminder_subscriptions_scope') IS NULL
       AND to_regclass('config.idx_ticket_reminder_subscriptions_scope') IS NOT NULL THEN
        ALTER INDEX config.idx_ticket_reminder_subscriptions_scope RENAME TO idx_task_reminder_subscriptions_scope;
    END IF;
    IF to_regclass('config.idx_task_reminder_subscriptions_enabled') IS NULL
       AND to_regclass('config.idx_ticket_reminder_subscriptions_enabled') IS NOT NULL THEN
        ALTER INDEX config.idx_ticket_reminder_subscriptions_enabled RENAME TO idx_task_reminder_subscriptions_enabled;
    END IF;
    IF to_regclass('reporting.idx_task_reminder_executions_recent') IS NULL
       AND to_regclass('reporting.idx_ticket_reminder_executions_recent') IS NOT NULL THEN
        ALTER INDEX reporting.idx_ticket_reminder_executions_recent RENAME TO idx_task_reminder_executions_recent;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS config.task_reminder_subscriptions (
    id                   BIGSERIAL PRIMARY KEY,
    name                 TEXT NOT NULL,
    division             TEXT NOT NULL,
    assignee_group       TEXT,
    recipients           JSONB NOT NULL DEFAULT '[]'::JSONB,
    cc_recipients        JSONB NOT NULL DEFAULT '[]'::JSONB,
    subject              TEXT,
    frequency            TEXT NOT NULL DEFAULT 'DAILY'
                         CHECK (frequency IN ('DAILY','WEEKLY')),
    weekday              SMALLINT CHECK (weekday BETWEEN 0 AND 6),
    send_time            TIME NOT NULL DEFAULT '10:00',
    timezone             TEXT NOT NULL DEFAULT 'Africa/Johannesburg',
    max_records          INT NOT NULL DEFAULT 10000 CHECK (max_records BETWEEN 1 AND 50000),
    enabled              BOOLEAN NOT NULL DEFAULT FALSE,
    deleted              BOOLEAN NOT NULL DEFAULT FALSE,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE config.task_reminder_subscriptions ADD COLUMN IF NOT EXISTS frequency TEXT NOT NULL DEFAULT 'DAILY';
ALTER TABLE config.task_reminder_subscriptions ADD COLUMN IF NOT EXISTS weekday SMALLINT;
ALTER TABLE config.task_reminder_subscriptions ADD COLUMN IF NOT EXISTS send_time TIME NOT NULL DEFAULT '10:00';
ALTER TABLE config.task_reminder_subscriptions ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'Africa/Johannesburg';

CREATE INDEX IF NOT EXISTS idx_task_reminder_subscriptions_scope
    ON config.task_reminder_subscriptions(division, assignee_group)
    WHERE NOT deleted;

CREATE INDEX IF NOT EXISTS idx_task_reminder_subscriptions_enabled
    ON config.task_reminder_subscriptions(enabled, frequency, send_time)
    WHERE NOT deleted;

CREATE TABLE IF NOT EXISTS reporting.task_reminder_executions (
    id                  BIGSERIAL PRIMARY KEY,
    subscription_id     BIGINT NOT NULL REFERENCES config.task_reminder_subscriptions(id),
    idempotency_key     TEXT NOT NULL,
    trigger_source      TEXT NOT NULL CHECK (trigger_source IN ('AUTOMATION','MANUAL')),
    status              TEXT NOT NULL CHECK (status IN ('RUNNING','SENT','FAILED')),
    recipients          JSONB NOT NULL DEFAULT '[]'::JSONB,
    record_count        INT NOT NULL DEFAULT 0,
    attention_count     INT NOT NULL DEFAULT 0,
    provider            TEXT,
    provider_message_id TEXT,
    error_code          TEXT,
    error_message       TEXT,
    requested_by        TEXT,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    UNIQUE (subscription_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_task_reminder_executions_recent
    ON reporting.task_reminder_executions(started_at DESC);
