"""
pipeline/load.py
================
Database loader. Manages ELT run lifecycle and bulk upsert.

Responsibilities:
  - Open / close run records in staging.elt_run_log.
  - Validate required fields; write rejected records to staging.elt_rejected_records.
  - Bulk upsert WorkOrderRecord batches into staging.raw_work_orders.
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
from pipeline.models import WorkOrderRecord

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
        cur.execute(sql, (run_id, source_entity, json.dumps(raw, default=str), reason))


# ---------------------------------------------------------------------------
# Work Order upsert
# ---------------------------------------------------------------------------

WORK_ORDER_COLUMNS = (
    "run_id", "work_order_id", "summary", "work_order_type", "category_tier1",
    "status", "status_reason", "priority", "requester", "support_group",
    "assignee", "notes", "submit_date", "target_date", "completed_date",
    "last_modified", "division", "report_category", "sla_status", "hours_open",
    "days_to_target", "is_open", "is_excluded", "source", "raw_payload",
)


def _work_order_row(rec: WorkOrderRecord, run_id: int, source: Optional[str]) -> tuple:
    return (
        run_id,
        rec.work_order_id,
        rec.summary,
        rec.work_order_type,
        rec.category_tier1,
        rec.status,
        rec.status_reason,
        rec.priority,
        rec.requester,
        rec.support_group,
        rec.assignee,
        rec.notes,
        rec.submit_date,
        rec.target_date,
        rec.completed_date,
        rec.last_modified,
        rec.division,
        rec.report_category,
        rec.sla_status,
        rec.hours_open,
        rec.days_to_target,
        rec.is_open,
        rec.is_excluded,
        source or rec.source,
        json.dumps(rec.raw_payload, default=str) if rec.raw_payload else None,
    )


UPSERT_SQL = f"""
    INSERT INTO staging.raw_work_orders ({", ".join(WORK_ORDER_COLUMNS)}, loaded_at)
    VALUES ({", ".join(["%s"] * len(WORK_ORDER_COLUMNS))}, NOW())
    ON CONFLICT (work_order_id) DO UPDATE SET
        {", ".join(f"{column} = EXCLUDED.{column}" for column in WORK_ORDER_COLUMNS if column != "work_order_id")},
        loaded_at = NOW()
"""


def load_work_orders(
    records: List[WorkOrderRecord],
    run_id:  int,
    source:  Optional[str] = None,
) -> tuple[int, int]:
    """
    Bulk upsert a batch of WorkOrderRecord objects into staging.raw_work_orders.

    Conflict key: work_order_id. On conflict every mutable field is updated.
    Returns (rows_loaded, rows_rejected).
    """
    if not records:
        return 0, 0

    rows_rejected = 0
    batch_rows = []
    for rec in records:
        if not rec.work_order_id:
            _write_rejected(run_id, "work_orders", rec.raw_payload or {}, "missing work_order_id")
            rows_rejected += 1
            continue
        batch_rows.append(_work_order_row(rec, run_id, source))

    if not batch_rows:
        return 0, rows_rejected

    with get_cursor() as cur:
        psycopg2.extras.execute_batch(cur, UPSERT_SQL, batch_rows, page_size=PAGE_SIZE)

    logger.info("Upserted %d Work Orders (run_id=%d source=%s)", len(batch_rows), run_id, source or "record")
    return len(batch_rows), rows_rejected


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
