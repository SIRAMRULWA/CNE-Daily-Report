"""
Delete report/pipeline data for one report date while preserving logs.

Use this when the wrong source was loaded for a day and the day must be
reloaded from the correct source.

Default mode is dry-run. Pass --execute to commit deletes.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(dotenv_path=ROOT / ".env")

from pipeline.db import _build_dsn, get_cursor, run_query, test_connection  # noqa: E402

SAST = timezone(timedelta(hours=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete report data for a selected date while preserving logs."
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Report date to clean in YYYY-MM-DD format, for example 2026-07-15.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows. Without this flag the script only prints counts.",
    )
    parser.add_argument(
        "--reset-helix-watermark",
        action="store_true",
        help=(
            "Also remove the helix_api/TMS:Task watermark. Use only if the wrong "
            "run advanced an incremental watermark and the next run must refetch."
        ),
    )
    return parser.parse_args()


def table_exists(schema: str, table: str) -> bool:
    rows = run_query(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
        ) AS exists
        """,
        (schema, table),
    )
    return bool(rows[0]["exists"])


def count_rows(sql: str, params: tuple) -> int:
    rows = run_query(sql, params)
    return int(rows[0]["count"]) if rows else 0


def clean_date(target_date: date, execute: bool, reset_helix_watermark: bool) -> None:
    day_start = datetime.combine(target_date, time.min, tzinfo=SAST)
    day_end = day_start + timedelta(days=1)

    parsed = urlparse(_build_dsn())
    print("Checking database connection...")
    test_connection()
    print(
        "Target DB: "
        f"host={parsed.hostname} port={parsed.port} "
        f"database={parsed.path.lstrip('/')} user={parsed.username}"
    )
    print(f"Cleanup date: {target_date.isoformat()} [{day_start.isoformat()}, {day_end.isoformat()})")
    print(f"Mode: {'EXECUTE' if execute else 'DRY RUN'}")

    targets = [
        (
            "reporting.daily_report_success_closures",
            table_exists("reporting", "daily_report_success_closures"),
            "report_date = %s",
            (target_date,),
        ),
        (
            "reporting.daily_report_records",
            table_exists("reporting", "daily_report_records"),
            "report_date = %s",
            (target_date,),
        ),
        (
            "reporting.daily_report_summary",
            table_exists("reporting", "daily_report_summary"),
            "report_date = %s",
            (target_date,),
        ),
        (
            "staging.raw_changes",
            table_exists("staging", "raw_changes"),
            "loaded_at >= %s AND loaded_at < %s",
            (day_start, day_end),
        ),
    ]

    preserve_checks = [
        (
            "staging.elt_run_log",
            table_exists("staging", "elt_run_log"),
            "run_start >= %s AND run_start < %s",
            (day_start, day_end),
        ),
        (
            "staging.elt_rejected_records",
            table_exists("staging", "elt_rejected_records"),
            "rejected_at >= %s AND rejected_at < %s",
            (day_start, day_end),
        ),
        (
            "config.activity_log",
            table_exists("config", "activity_log"),
            "created_at >= %s AND created_at < %s",
            (day_start, day_end),
        ),
        (
            "config.login_history",
            table_exists("config", "login_history"),
            "login_time >= %s AND login_time < %s",
            (day_start, day_end),
        ),
    ]

    print("\nRows selected for deletion:")
    for table, exists, where_sql, params in targets:
        if not exists:
            print(f"  {table}: table missing")
            continue
        total = count_rows(f"SELECT COUNT(*) AS count FROM {table} WHERE {where_sql}", params)
        print(f"  {table}: {total}")

    print("\nLogs/control rows preserved:")
    for table, exists, where_sql, params in preserve_checks:
        if not exists:
            print(f"  {table}: table missing")
            continue
        total = count_rows(f"SELECT COUNT(*) AS count FROM {table} WHERE {where_sql}", params)
        print(f"  {table}: {total}")

    if table_exists("staging", "elt_watermarks"):
        watermark_rows = run_query(
            """
            SELECT source_name, entity_name, watermark_to, updated_at
            FROM staging.elt_watermarks
            ORDER BY updated_at DESC
            """
        )
        print("\nWatermarks preserved:")
        for row in watermark_rows:
            print(
                "  "
                f"{row['source_name']}/{row['entity_name']} "
                f"watermark_to={row['watermark_to']} updated_at={row['updated_at']}"
            )

    if not execute:
        print("\nDry run complete. Re-run with --execute to delete these rows.")
        return

    print("\nDeleting selected rows...")
    with get_cursor() as cur:
        for table, exists, where_sql, params in targets:
            if not exists:
                continue
            cur.execute(f"DELETE FROM {table} WHERE {where_sql}", params)
            print(f"  {table}: deleted {cur.rowcount}")

        if reset_helix_watermark and table_exists("staging", "elt_watermarks"):
            cur.execute(
                """
                DELETE FROM staging.elt_watermarks
                WHERE source_name = %s
                  AND entity_name = %s
                """,
                ("helix_api", "TMS:Task"),
            )
            print(f"  staging.elt_watermarks helix_api/TMS:Task: deleted {cur.rowcount}")

    print("\nCleanup committed. Logs were preserved.")


def main() -> None:
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    clean_date(
        target_date=target_date,
        execute=args.execute,
        reset_helix_watermark=args.reset_helix_watermark,
    )


if __name__ == "__main__":
    main()
