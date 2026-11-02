-- =============================================================
-- Work Order Report — Database Schema
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
-- RAW WORK ORDERS (staging)
-- One row per Helix Work Order; refreshed by every pipeline run.
-- =============================================================

CREATE TABLE IF NOT EXISTS staging.raw_work_orders (
    id               BIGSERIAL PRIMARY KEY,
    run_id           BIGINT REFERENCES staging.elt_run_log(run_id),

    -- identifier
    work_order_id    TEXT NOT NULL UNIQUE,

    -- source fields
    summary          TEXT,
    work_order_type  TEXT,
    category_tier1   TEXT,
    status           TEXT,
    status_reason    TEXT,
    priority         TEXT,
    requester        TEXT,
    support_group    TEXT,
    assignee         TEXT,
    notes            TEXT,

    -- timestamps (workspace-local)
    submit_date      TIMESTAMP,
    target_date      TIMESTAMP,
    completed_date   TIMESTAMP,
    last_modified    TIMESTAMP,

    -- derived (populated by the pipeline transform layer)
    division         TEXT,
    report_category  TEXT,
    sla_status       TEXT,  -- WITHIN_SLA / NEARING_SLA / BREACHED / NO_TARGET_DATE / MET_TARGET / MISSED_TARGET / OUT_OF_SCOPE
    hours_open       NUMERIC(10,2),
    days_to_target   INTEGER,  -- negative = days overdue
    is_open          BOOLEAN NOT NULL DEFAULT FALSE,
    is_excluded      BOOLEAN NOT NULL DEFAULT FALSE,

    -- metadata
    source           TEXT NOT NULL DEFAULT 'helix_api'
                     CHECK (source IN ('excel', 'csv', 'helix_api')),
    raw_payload      JSONB,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_work_orders_support_group ON staging.raw_work_orders(support_group);
CREATE INDEX IF NOT EXISTS idx_raw_work_orders_division      ON staging.raw_work_orders(division);
CREATE INDEX IF NOT EXISTS idx_raw_work_orders_sla_status    ON staging.raw_work_orders(sla_status);
CREATE INDEX IF NOT EXISTS idx_raw_work_orders_target_date   ON staging.raw_work_orders(target_date);
CREATE INDEX IF NOT EXISTS idx_raw_work_orders_run_id        ON staging.raw_work_orders(run_id);
CREATE INDEX IF NOT EXISTS idx_raw_work_orders_loaded_at     ON staging.raw_work_orders(loaded_at);

-- =============================================================
-- REPORTING TABLES
-- The wo_* tables are written by dbt (one immutable snapshot per
-- report_date). They are created here so the API answers with empty
-- results, not errors, before the first pipeline run. Column lists must
-- match the dbt models in dbt/models/marts.
-- =============================================================

-- Singleton heartbeat row for pipeline freshness monitoring
CREATE TABLE IF NOT EXISTS reporting.pipeline_heartbeat (
    id              INT PRIMARY KEY DEFAULT 1,
    last_run_at     TIMESTAMPTZ,
    last_run_status TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CHECK (id = 1)   -- enforce singleton
);

INSERT INTO reporting.pipeline_heartbeat (id, last_run_at, last_run_status)
VALUES (1, NULL, 'NEVER')
ON CONFLICT (id) DO NOTHING;

-- Open Work Orders per report date (dbt: wo_report_records)
CREATE TABLE IF NOT EXISTS reporting.wo_report_records (
    report_date      DATE NOT NULL,
    work_order_id    TEXT NOT NULL,
    division         TEXT,
    support_group    TEXT,
    report_category  TEXT,
    sla_status       TEXT,
    priority         TEXT,
    status           TEXT,
    status_reason    TEXT,
    requester        TEXT,
    assignee         TEXT,
    summary          TEXT,
    hours_open       NUMERIC,
    days_to_target   INTEGER,
    submit_date      TIMESTAMP,
    target_date      TIMESTAMP,
    completed_date   TIMESTAMP,
    source           TEXT,
    run_id           BIGINT,
    loaded_at        TIMESTAMPTZ,
    snapshotted_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_wo_records_date  ON reporting.wo_report_records(report_date);
CREATE INDEX IF NOT EXISTS idx_wo_records_scope ON reporting.wo_report_records(division, support_group);

-- Division x support group x SLA counts per report date (dbt: wo_report_summary)
CREATE TABLE IF NOT EXISTS reporting.wo_report_summary (
    report_date      DATE NOT NULL,
    division         TEXT NOT NULL,
    support_group    TEXT NOT NULL,
    within_count     BIGINT NOT NULL DEFAULT 0,
    nearing_count    BIGINT NOT NULL DEFAULT 0,
    breached_count   BIGINT NOT NULL DEFAULT 0,
    no_target_count  BIGINT NOT NULL DEFAULT 0,
    total_open       BIGINT NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_wo_summary_date  ON reporting.wo_report_summary(report_date);
CREATE INDEX IF NOT EXISTS idx_wo_summary_scope ON reporting.wo_report_summary(division, support_group);

-- Work Orders completed in the previous 07:00-07:00 window (dbt: wo_completed)
CREATE TABLE IF NOT EXISTS reporting.wo_completed (
    report_date      DATE NOT NULL,
    window_start     TIMESTAMP,
    window_end       TIMESTAMP,
    work_order_id    TEXT NOT NULL,
    division         TEXT,
    support_group    TEXT,
    report_category  TEXT,
    sla_status       TEXT,   -- MET_TARGET / MISSED_TARGET / NO_TARGET_DATE
    priority         TEXT,
    status           TEXT,
    requester        TEXT,
    assignee         TEXT,
    summary          TEXT,
    hours_open       NUMERIC,
    days_to_target   INTEGER,
    submit_date      TIMESTAMP,
    target_date      TIMESTAMP,
    completed_date   TIMESTAMP,
    snapshotted_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_wo_completed_date  ON reporting.wo_completed(report_date);
CREATE INDEX IF NOT EXISTS idx_wo_completed_scope ON reporting.wo_completed(division, support_group);
