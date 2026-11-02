"""
pipeline/load.py
================
Database loader. Manages ELT run lifecycle and bulk upsert.

Responsibilities:
  - Open / close run records in staging.elt_run_log.
  - Validate required fields; write rejected records to staging.elt_rejected_records.
  - Bulk upsert ChangeRecord batches into staging.raw_changes.
  - Update reporting.pipeline_heartbeat after successful runs.
  - Provide watermark helpers for future incremental Helix API ingestion.
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Optional

import psycopg2.extras

from pipeline.db import get_cursor
from pipeline.models import ChangeRecord

logger = logging.getLogger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
PAGE_SIZE   = 200   # psycopg2 execute_batch page size


def _naive_datetime(value: Optional[datetime]) -> Optional[datetime]:
    """Return datetimes in the naive shape used by the transform layer."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Run log helpers
# ---------------------------------------------------------------------------

def open_run(
    pipeline_name: str,
    source_entity: str,
    source_file:   Optional[str] = None,
) -> int:
    """Insert a RUNNING row into staging.elt_run_log. Returns run_id."""
    sql = """
        INSERT INTO staging.elt_run_log
            (pipeline_name, source_entity, source_file, run_start, status, environment)
        VALUES (%s, %s, %s, NOW(), 'RUNNING', %s)
        RETURNING run_id
    """
    with get_cursor() as cur:
        cur.execute(sql, (pipeline_name, source_entity, source_file, ENVIRONMENT))
        run_id = cur.fetchone()["run_id"]
    logger.info("Opened run %d (%s / %s)", run_id, pipeline_name, source_entity)
    return run_id


def close_run(
    run_id:         int,
    status:         str,
    rows_extracted: int = 0,
    rows_loaded:    int = 0,
    rows_rejected:  int = 0,
    error_message:  Optional[str] = None,
) -> None:
    """Update the run log row with final metrics."""
    sql = """
        UPDATE staging.elt_run_log
        SET run_end       = NOW(),
            status        = %s,
            rows_extracted = %s,
            rows_loaded   = %s,
            rows_rejected = %s,
            error_message = %s
        WHERE run_id = %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (status, rows_extracted, rows_loaded, rows_rejected,
                          error_message, run_id))
    logger.info("Closed run %d with status=%s (loaded=%d rejected=%d)",
                run_id, status, rows_loaded, rows_rejected)


# ---------------------------------------------------------------------------
# Rejected record capture
# ---------------------------------------------------------------------------

def _write_rejected(run_id: int, source_entity: str, raw: dict, reason: str) -> None:
    sql = """
        INSERT INTO staging.elt_rejected_records
            (run_id, source_entity, raw_data, rejection_reason, rejected_at)
        VALUES (%s, %s, %s, %s, NOW())
    """
    with get_cursor() as cur:
        cur.execute(sql, (run_id, source_entity, json.dumps(raw), reason))


# ---------------------------------------------------------------------------
# Change record upsert
# ---------------------------------------------------------------------------

def load_changes(
    records: List[ChangeRecord],
    run_id:  int,
    source:  Optional[str] = None,
) -> tuple[int, int]:
    """
    Bulk upsert a batch of ChangeRecord objects into staging.raw_changes.

    Conflict key: (request_id, task_id).
    On conflict: update all mutable fields.

    Returns (rows_loaded, rows_rejected).
    """
    if not records:
        return 0, 0

    rows_loaded   = 0
    rows_rejected = 0
    batch_rows    = []

    for rec in records:
        # Validation — only request_id is hard-required
        if not rec.request_id:
            _write_rejected(run_id, "changes", rec.raw_payload or {}, "missing request_id")
            rows_rejected += 1
            continue

        batch_rows.append((
            run_id,
            rec.request_id,
            rec.task_id or "",
            rec.op_cat_tier1,
            rec.summary,
            rec.assignee,
            rec.priority,
            rec.status,
            rec.status_reason,
            rec.assignee_group,
            rec.notes,
            rec.create_date,
            rec.assign_time,
            rec.closed_time,
            rec.scheduled_start,
            rec.scheduled_end,
            rec.report_group,
            rec.report_category,
            rec.sla_status,
            rec.hours_open,
            rec.exclude_change,
            rec.exclude_incident,
            source or rec.source,
            json.dumps(rec.raw_payload) if rec.raw_payload else None,
        ))

    if not batch_rows:
        return 0, rows_rejected

    upsert_sql = """
        INSERT INTO staging.raw_changes (
            run_id, request_id, task_id, op_cat_tier1, summary,
            assignee, priority, status, status_reason, assignee_group, notes,
            create_date, assign_time, closed_time, scheduled_start, scheduled_end,
            report_group, report_category, sla_status, hours_open,
            exclude_change, exclude_incident,
            source, raw_payload, loaded_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, NOW()
        )
        ON CONFLICT (request_id, task_id) DO UPDATE SET
            run_id          = EXCLUDED.run_id,
            op_cat_tier1    = EXCLUDED.op_cat_tier1,
            summary         = EXCLUDED.summary,
            assignee        = EXCLUDED.assignee,
            priority        = EXCLUDED.priority,
            status          = EXCLUDED.status,
            status_reason   = EXCLUDED.status_reason,
            assignee_group  = EXCLUDED.assignee_group,
            notes           = EXCLUDED.notes,
            create_date     = EXCLUDED.create_date,
            assign_time     = EXCLUDED.assign_time,
            closed_time     = EXCLUDED.closed_time,
            scheduled_start = EXCLUDED.scheduled_start,
            scheduled_end   = EXCLUDED.scheduled_end,
            report_group    = EXCLUDED.report_group,
            report_category = EXCLUDED.report_category,
            sla_status      = EXCLUDED.sla_status,
            hours_open      = EXCLUDED.hours_open,
            exclude_change  = EXCLUDED.exclude_change,
            exclude_incident = EXCLUDED.exclude_incident,
            source          = EXCLUDED.source,
            raw_payload     = EXCLUDED.raw_payload,
            loaded_at       = NOW()
    """

    with get_cursor() as cur:
        psycopg2.extras.execute_batch(cur, upsert_sql, batch_rows, page_size=PAGE_SIZE)
        rows_loaded = len(batch_rows)

    logger.info("Upserted %d records (run_id=%d source=%s)", rows_loaded, run_id, source or "record")
    return rows_loaded, rows_rejected


# ---------------------------------------------------------------------------
# Heartbeat update
# ---------------------------------------------------------------------------

def update_heartbeat(status: str) -> None:
    """Update the singleton reporting.pipeline_heartbeat row."""
    sql = """
        INSERT INTO reporting.pipeline_heartbeat (id, last_run_at, last_run_status, updated_at)
        VALUES (1, NOW(), %s, NOW())
        ON CONFLICT (id) DO UPDATE SET
            last_run_at     = NOW(),
            last_run_status = EXCLUDED.last_run_status,
            updated_at      = NOW()
    """
    with get_cursor() as cur:
        cur.execute(sql, (status,))
    logger.info("Heartbeat updated: %s", status)


# ---------------------------------------------------------------------------
# Watermark helpers
# ---------------------------------------------------------------------------

def _watermark_column() -> str:
    """
    Return the available watermark timestamp column.

    New schemas use watermark_to. Older local databases used last_extracted,
    so keep both working without forcing a manual migration first.
    """
    try:
        from pipeline.db import run_query
        rows = run_query(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'staging'
              AND table_name = 'elt_watermarks'
              AND column_name IN ('watermark_to', 'last_extracted')
            ORDER BY CASE column_name WHEN 'watermark_to' THEN 0 ELSE 1 END
            """
        )
        if rows:
            return rows[0]["column_name"]
    except Exception as exc:
        logger.warning("Could not inspect watermark table: %s", exc)
    return "watermark_to"


def get_watermark(source_name: str, entity_name: str) -> Optional[datetime]:
    """Return the last processed timestamp for a source/entity pair."""
    rows = []
    try:
        from pipeline.db import run_query
        column = _watermark_column()
        rows = run_query(
            f"SELECT {column} AS watermark_value FROM staging.elt_watermarks "
            "WHERE source_name = %s AND entity_name = %s",
            (source_name, entity_name),
        )
    except Exception as exc:
        logger.warning("Could not read watermark: %s", exc)
    return _naive_datetime(rows[0]["watermark_value"]) if rows else None


def set_watermark(source_name: str, entity_name: str, watermark: datetime) -> None:
    """Upsert the watermark for a source/entity pair."""
    column = _watermark_column()
    sql = f"""
        INSERT INTO staging.elt_watermarks (source_name, entity_name, {column})
        VALUES (%s, %s, %s)
        ON CONFLICT (source_name, entity_name) DO UPDATE SET
            {column} = EXCLUDED.{column},
            updated_at = NOW()
    """
    with get_cursor() as cur:
        cur.execute(sql, (source_name, entity_name, _naive_datetime(watermark)))
