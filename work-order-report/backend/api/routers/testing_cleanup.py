"""Super-admin-only, explicitly enabled test-data cleanup endpoint."""

import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

from api.auth import AuthenticatedUser, Role, audit_event, require_roles
from pipeline.db import get_cursor, run_query


ALLOWED_ENVIRONMENTS = {"dev", "development", "test", "testing", "qa"}


class CleanupRequest(BaseModel):
    report_date: date
    execute: bool = False
    confirmation: str | None = None
    reset_helix_watermark: bool = False


def _enabled() -> bool:
    return os.getenv("TEST_DATA_CLEANUP_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _assert_available() -> None:
    environment = os.getenv("ENVIRONMENT", "dev").strip().lower()
    if not _enabled():
        raise HTTPException(status_code=404, detail="Testing cleanup endpoint is disabled")
    if environment not in ALLOWED_ENVIRONMENTS:
        raise HTTPException(
            status_code=403,
            detail="Testing cleanup is not permitted in this environment",
        )


def _table_exists(schema: str, table: str) -> bool:
    rows = run_query("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"{schema}.{table}",))
    return bool(rows and rows[0]["exists"])


def _targets(report_date: date) -> list[tuple[str, str, tuple]]:
    timezone = ZoneInfo(os.getenv("WORKSPACE_TIMEZONE", "Africa/Johannesburg"))
    day_start = datetime.combine(report_date, time.min, tzinfo=timezone)
    day_end = day_start + timedelta(days=1)
    return [
        ("reporting.daily_report_success_closures", "report_date = %s", (report_date,)),
        ("reporting.daily_report_records", "report_date = %s", (report_date,)),
        ("reporting.daily_report_summary", "report_date = %s", (report_date,)),
        ("staging.raw_changes", "loaded_at >= %s AND loaded_at < %s", (day_start, day_end)),
    ]


def _counts(report_date: date) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for table, where_sql, params in _targets(report_date):
        schema, table_name = table.split(".", 1)
        if not _table_exists(schema, table_name):
            result[table] = None
            continue
        rows = run_query(f"SELECT COUNT(*) AS count FROM {table} WHERE {where_sql}", params)
        result[table] = int(rows[0]["count"]) if rows else 0
    return result


def cleanup_test_data(
    payload: CleanupRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_roles(Role.SUPER_ADMIN)),
):
    """Preview or delete one date's report/raw data while preserving logs and config."""
    _assert_available()
    expected_confirmation = f"DELETE {payload.report_date.isoformat()}"
    if payload.execute and payload.confirmation != expected_confirmation:
        raise HTTPException(
            status_code=422,
            detail=f"Set confirmation to {expected_confirmation!r} to execute cleanup",
        )

    selected = _counts(payload.report_date)
    deleted = {table: 0 if count is not None else None for table, count in selected.items()}
    watermark_deleted = 0

    if payload.execute:
        with get_cursor() as cur:
            for table, where_sql, params in _targets(payload.report_date):
                if selected.get(table) is None:
                    continue
                cur.execute(f"DELETE FROM {table} WHERE {where_sql}", params)
                deleted[table] = cur.rowcount

            if payload.reset_helix_watermark and _table_exists("staging", "elt_watermarks"):
                cur.execute(
                    """
                    DELETE FROM staging.elt_watermarks
                    WHERE source_name = %s AND entity_name = %s
                    """,
                    ("helix_api", "TMS:Task"),
                )
                watermark_deleted = cur.rowcount

    audit_event(
        action="execute_test_data_cleanup" if payload.execute else "preview_test_data_cleanup",
        entity_type="test_data_cleanup",
        entity_id=payload.report_date.isoformat(),
        actor=current_user.email,
        request=request,
        details={
            "report_date": payload.report_date.isoformat(),
            "selected": selected,
            "deleted": deleted,
            "reset_helix_watermark": payload.reset_helix_watermark,
            "watermark_deleted": watermark_deleted,
        },
    )

    return {
        "mode": "EXECUTE" if payload.execute else "DRY_RUN",
        "report_date": payload.report_date,
        "selected": selected,
        "deleted": deleted,
        "watermark_deleted": watermark_deleted,
        "logs_preserved": True,
        "required_confirmation": None if payload.execute else expected_confirmation,
    }
