"""
pipeline/activity_log.py
========================
Audit trail helpers for API-driven configuration changes.
"""

from typing import Any

from psycopg2.extras import Json

from app_core.settings import env_flag
from pipeline.db import get_cursor, run_query


def ensure_activity_log_table() -> None:
    with get_cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS config")
        cur.execute(
            """
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
            )
            """
        )
        cur.execute("ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS ip_address TEXT")
        cur.execute("ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS user_agent TEXT")
        cur.execute("ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS browser TEXT")
        cur.execute("ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS operating_system TEXT")
        cur.execute("ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS result TEXT")
        cur.execute("ALTER TABLE config.activity_log ADD COLUMN IF NOT EXISTS request_id TEXT")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_log_created_at "
            "ON config.activity_log(created_at DESC)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_log_entity "
            "ON config.activity_log(entity_type, entity_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_log_request_id "
            "ON config.activity_log(request_id) WHERE request_id IS NOT NULL"
        )


def record_activity(
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    actor: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    if env_flag("RUNTIME_SCHEMA_BOOTSTRAP_ENABLED", False):
        ensure_activity_log_table()
    details = details or {}
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO config.activity_log
                (
                    action,
                    entity_type,
                    entity_id,
                    actor,
                    details,
                    ip_address,
                    user_agent,
                    browser,
                    operating_system,
                    result
                    , request_id
                )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                action,
                entity_type,
                entity_id,
                actor,
                Json(details),
                details.get("ip_address"),
                details.get("user_agent"),
                details.get("browser"),
                details.get("operating_system"),
                details.get("result"),
                details.get("request_id"),
            ),
        )


def list_activity(
    entity_type: str | None = None,
    entity_types: list[str] | None = None,
    entity_id_prefix: str | None = None,
    actor: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    if env_flag("RUNTIME_SCHEMA_BOOTSTRAP_ENABLED", False):
        ensure_activity_log_table()
    conditions = []
    params: list = []

    if entity_type:
        conditions.append("entity_type = %s")
        params.append(entity_type)
    if entity_types:
        cleaned_entity_types = [value.strip() for value in entity_types if value and value.strip()]
        if cleaned_entity_types:
            conditions.append("entity_type = ANY(%s)")
            params.append(cleaned_entity_types)
    if entity_id_prefix:
        conditions.append("entity_id LIKE %s")
        params.append(f"{entity_id_prefix}%")
    if actor:
        conditions.append("actor = %s")
        params.append(actor)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.extend([limit, offset])

    return run_query(
        f"""
        SELECT
            id,
            action,
            entity_type,
            entity_id,
            actor,
            details,
            ip_address,
            user_agent,
            browser,
            operating_system,
            result,
            request_id,
            created_at
        FROM config.activity_log
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    )
