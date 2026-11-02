"""Database retention enforcement for operational report data.

Business payloads are kept for seven days by default.  Audit, security,
configuration, delivery-history, and pipeline-run metadata are deliberately
outside the purge allowlist.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from psycopg2.extras import Json

from pipeline.db import get_cursor

logger = logging.getLogger(__name__)

ADVISORY_LOCK_ID = 1_346_782_902
DEFAULT_RETENTION_DAYS = 7


@dataclass(frozen=True)
class PurgeTarget:
    table: str
    predicate: str


# This is intentionally an allowlist.  Never add audit/configuration tables
# here merely because they contain a timestamp.
SNAPSHOT_PREDICATE = "report_date < ((CURRENT_TIMESTAMP AT TIME ZONE %s)::date - (%s - 1))"

PURGE_TARGETS = (
    PurgeTarget("reporting.wo_report_records", SNAPSHOT_PREDICATE),
    PurgeTarget("reporting.wo_report_summary", SNAPSHOT_PREDICATE),
    PurgeTarget("reporting.wo_completed", SNAPSHOT_PREDICATE),
    PurgeTarget(
        "staging.elt_rejected_records",
        "rejected_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')",
    ),
    PurgeTarget(
        "staging.raw_work_orders",
        "loaded_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')",
    ),
)


def _positive_days(value: str | int | None) -> int:
    days = int(value if value is not None else DEFAULT_RETENTION_DAYS)
    if days < 1:
        raise ValueError("DATA_RETENTION_DAYS must be at least 1")
    return days


def enforce_retention(
    days: int = DEFAULT_RETENTION_DAYS,
    timezone: str = "Africa/Johannesburg",
) -> dict[str, int]:
    """Purge expired business payloads transactionally and audit the result."""
    days = _positive_days(days)
    deleted: dict[str, int] = {}

    with get_cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_ID,))
        for target in PURGE_TARGETS:
            cur.execute("SELECT to_regclass(%s) AS relation", (target.table,))
            relation = cur.fetchone()["relation"]
            if relation is None:
                deleted[target.table] = 0
                continue

            params = (
                (timezone, days)
                if target.table.startswith("reporting.")
                else (days,)
            )
            cur.execute(
                f"DELETE FROM {target.table} WHERE {target.predicate}",
                params,
            )
            deleted[target.table] = cur.rowcount

        details = {
            "retention_days": days,
            "timezone": timezone,
            "deleted": deleted,
            "preserved_categories": [
                "audit",
                "security",
                "configuration",
                "delivery_history",
                "pipeline_run_metadata",
            ],
        }
        cur.execute(
            """
            INSERT INTO config.activity_log
                (action, entity_type, actor, details, result)
            VALUES
                ('enforce_data_retention', 'data_retention', 'system', %s, 'SUCCESS')
            """,
            (Json(details),),
        )

    logger.info(
        "Data retention complete: %s",
        json.dumps({"retention_days": days, "deleted": deleted}, sort_keys=True),
    )
    return deleted


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    days = _positive_days(os.getenv("DATA_RETENTION_DAYS"))
    timezone = os.getenv("WORKSPACE_TIMEZONE", "Africa/Johannesburg").strip()
    enforce_retention(days=days, timezone=timezone)


if __name__ == "__main__":
    main()
