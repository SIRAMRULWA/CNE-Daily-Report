"""
pipeline/run.py
===============
Work Order Report - Pipeline Orchestrator.

Coordinates file or Helix API ingestion through the same transform, load, dbt,
and heartbeat flow.
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

# Allow running from project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

from app_core.clock import workspace_now_naive
from pipeline.db import test_connection
from pipeline.extract import archive_file, extract_file, get_pending_files
from pipeline.load import close_run, get_watermark, load_work_orders, open_run, set_watermark, update_heartbeat
from pipeline.transform import transform_records

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline.run")

EXCEL_DROP_DIR = os.getenv("EXCEL_DROP_DIR", "./data/excel_drop")
PIPELINE_NAME = "work_order_report"
SOURCE_ENTITY = "work_orders"
DBT_DIR = Path(__file__).parent.parent / "dbt"
HELIX_SOURCE_NAME = "helix_api"
HELIX_ENTITY_NAME = os.getenv("HELIX_FORM", "WOI:WorkOrder")


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _safe_close_run(
    run_id: int,
    status: str,
    rows_extracted: int = 0,
    rows_loaded: int = 0,
    rows_rejected: int = 0,
    error_message: str | None = None,
) -> None:
    """Close a run log without masking the original pipeline error."""
    try:
        close_run(
            run_id,
            status=status,
            rows_extracted=rows_extracted,
            rows_loaded=rows_loaded,
            rows_rejected=rows_rejected,
            error_message=error_message,
        )
    except Exception as exc:
        logger.warning("Could not close run %d with status=%s: %s", run_id, status, exc)


def _run_dbt(mode: str = "run") -> bool:
    """Execute dbt run/build against the dbt project."""
    if not DBT_DIR.exists():
        logger.warning("dbt directory not found at %s - skipping dbt", DBT_DIR)
        return False

    dbt_exe = shutil.which("dbt")
    if not dbt_exe:
        candidate = Path(sys.executable).with_name("dbt.exe" if os.name == "nt" else "dbt")
        if candidate.exists():
            dbt_exe = str(candidate)

    if not dbt_exe:
        logger.warning("dbt executable not found - skipping dbt")
        return False

    cmd = [dbt_exe, mode, "--profiles-dir", str(DBT_DIR), "--project-dir", str(DBT_DIR)]
    env = os.environ.copy()
    database_url = env.get("DATABASE_URL")
    if database_url:
        parsed = urlparse(database_url)
        if parsed.hostname:
            env["DB_HOST"] = parsed.hostname
        if parsed.port:
            env["DB_PORT"] = str(parsed.port)
        if parsed.path and len(parsed.path) > 1:
            env["DB_NAME"] = parsed.path.lstrip("/")
        if parsed.username:
            env["DB_USER"] = unquote(parsed.username)
        if parsed.password:
            env["DB_PASSWORD"] = unquote(parsed.password)

    attempts = max(int(os.getenv("DBT_RUN_RETRIES", "2")), 1)
    delay = max(float(os.getenv("DBT_RETRY_DELAY_SECONDS", "5")), 0)

    for attempt in range(1, attempts + 1):
        logger.info("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if result.returncode == 0:
            logger.info("dbt %s completed successfully", mode)
            return True

        logger.warning(
            "dbt %s failed on attempt %d/%d (exit %d):\n%s",
            mode,
            attempt,
            attempts,
            result.returncode,
            result.stderr or result.stdout,
        )
        if attempt < attempts and delay:
            logger.info("Retrying dbt %s in %.1fs", mode, delay)
            time.sleep(delay)

    return False


def _process_file(
    filepath: Path,
    as_of: datetime,
    archive: bool = True,
) -> tuple[bool, int, int, int]:
    """Run extract -> transform -> load for one CSV/Excel file."""
    run_id = open_run(PIPELINE_NAME, SOURCE_ENTITY, source_file=filepath.name)

    total_extracted = 0
    total_loaded = 0
    total_rejected = 0
    success = True

    try:
        for batch in extract_file(filepath):
            total_extracted += len(batch)
            transform_records(batch, as_of=as_of)
            loaded, rejected = load_work_orders(batch, run_id=run_id)
            total_loaded += loaded
            total_rejected += rejected

        if archive:
            archive_file(filepath)

        _safe_close_run(
            run_id,
            status="SUCCESS",
            rows_extracted=total_extracted,
            rows_loaded=total_loaded,
            rows_rejected=total_rejected,
        )
        logger.info(
            "File OK: %s | extracted=%d loaded=%d rejected=%d",
            filepath.name,
            total_extracted,
            total_loaded,
            total_rejected,
        )

    except Exception as exc:
        success = False
        logger.error("File FAILED: %s - %s", filepath.name, exc, exc_info=True)
        _safe_close_run(
            run_id,
            status="FAILED",
            rows_extracted=total_extracted,
            rows_loaded=total_loaded,
            rows_rejected=total_rejected,
            error_message=str(exc),
        )

    return success, total_extracted, total_loaded, total_rejected


def _period_bounds(period: str | None) -> tuple[str | None, str | None]:
    """Resolve simple Helix period keywords to YYYY-MM-DD strings."""
    if not period:
        return None, None

    today = datetime.today().date()
    if period == "today":
        start = end = today
    elif period == "yesterday":
        start = end = today - timedelta(days=1)
    elif period == "last-7-days":
        start = today - timedelta(days=7)
        end = today
    else:
        raise ValueError("Unsupported Helix period")

    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _helix_watermark_value(record) -> datetime | None:
    """Return the record timestamp matching HELIX_DATE_FIELD."""
    field = os.getenv("HELIX_DATE_FIELD", "Submit Date").strip().lower()
    field_map = {
        "submit date": record.submit_date,
        "last modified date": record.last_modified,
        "completed date": record.completed_date,
    }
    return field_map.get(field, record.submit_date)


def _process_helix(
    as_of: datetime,
    start_date: str | None = None,
    end_date: str | None = None,
    period: str | None = None,
) -> tuple[bool, int, int, int]:
    """Run Helix API extract -> transform -> load."""
    from helix.extractor import HelixExtractor

    extractor = HelixExtractor()
    if not extractor.is_configured():
        logger.error("Helix source requested, but HELIX_BASE_URL and credentials are not configured")
        return False, 0, 0, 0

    period_start, period_end = _period_bounds(period)
    start_date = start_date or period_start
    end_date = end_date or period_end
    use_watermark = _env_flag("HELIX_USE_INCREMENTAL_WATERMARK", False)
    since = None if start_date or not use_watermark else get_watermark(HELIX_SOURCE_NAME, HELIX_ENTITY_NAME)

    run_id = open_run(PIPELINE_NAME, SOURCE_ENTITY, source_file="helix_api")
    total_extracted = 0
    total_loaded = 0
    total_rejected = 0
    latest_seen = since
    success = True

    try:
        for batch in extractor.extract_work_orders(since=since, start_date=start_date, end_date=end_date):
            total_extracted += len(batch)
            for record in batch:
                record_latest = _helix_watermark_value(record)
                if record_latest and (latest_seen is None or record_latest > latest_seen):
                    latest_seen = record_latest

            transform_records(batch, as_of=as_of)
            loaded, rejected = load_work_orders(batch, run_id=run_id, source=HELIX_SOURCE_NAME)
            total_loaded += loaded
            total_rejected += rejected

        if use_watermark:
            set_watermark(HELIX_SOURCE_NAME, HELIX_ENTITY_NAME, latest_seen or as_of)
        _safe_close_run(
            run_id,
            status="SUCCESS",
            rows_extracted=total_extracted,
            rows_loaded=total_loaded,
            rows_rejected=total_rejected,
        )
        logger.info(
            "Helix API OK | extracted=%d loaded=%d rejected=%d",
            total_extracted,
            total_loaded,
            total_rejected,
        )

    except Exception as exc:
        success = False
        logger.error("Helix API FAILED: %s", exc, exc_info=True)
        _safe_close_run(
            run_id,
            status="FAILED",
            rows_extracted=total_extracted,
            rows_loaded=total_loaded,
            rows_rejected=total_rejected,
            error_message=str(exc),
        )

    return success, total_extracted, total_loaded, total_rejected


def run(
    mode: str = "incremental",
    file_arg: str | None = None,
    as_of_arg: str | None = None,
    source: str = "file",
    helix_period: str | None = None,
    helix_start: str | None = None,
    helix_end: str | None = None,
) -> None:
    """Execute the full pipeline."""
    as_of = workspace_now_naive()
    if as_of_arg:
        try:
            as_of = datetime.strptime(as_of_arg, "%Y-%m-%d %H:%M")
            logger.info("Running as-of: %s", as_of)
        except ValueError:
            logger.error("--as-of must be YYYY-MM-DD HH:MM")
            sys.exit(1)

    logger.info("=" * 60)
    logger.info("Work Order Report - %s", as_of.strftime("%Y-%m-%d %H:%M"))
    logger.info("Mode: %s | Source: %s | Environment: %s", mode, source, os.getenv("ENVIRONMENT", "dev"))
    logger.info("=" * 60)

    try:
        test_connection()
    except Exception as exc:
        logger.critical("Cannot connect to database: %s", exc)
        sys.exit(1)

    overall_success = True
    grand_extracted = grand_loaded = grand_rejected = 0

    if source == "helix":
        ok, extracted, loaded, rejected = _process_helix(
            as_of=as_of,
            start_date=helix_start,
            end_date=helix_end,
            period=helix_period,
        )
        overall_success = ok
        grand_extracted += extracted
        grand_loaded += loaded
        grand_rejected += rejected
    else:
        if file_arg:
            files = [Path(file_arg)]
            do_archive = False
        else:
            files = get_pending_files(EXCEL_DROP_DIR)
            do_archive = True

        if not files:
            logger.info("No files to process.")
            update_heartbeat("SUCCESS")
            return

        for filepath in files:
            ok, extracted, loaded, rejected = _process_file(filepath, as_of, archive=do_archive)
            if not ok:
                overall_success = False
            grand_extracted += extracted
            grand_loaded += loaded
            grand_rejected += rejected

    logger.info(
        "All records processed | extracted=%d loaded=%d rejected=%d",
        grand_extracted,
        grand_loaded,
        grand_rejected,
    )

    if overall_success:
        overall_success = _run_dbt("run")
    else:
        logger.warning("Skipping dbt due to pipeline failures")

    heartbeat_status = "SUCCESS" if overall_success else "PARTIAL"
    try:
        update_heartbeat(heartbeat_status)
    except Exception as exc:
        logger.warning("Heartbeat update failed: %s", exc)

    logger.info("Pipeline complete - %s", heartbeat_status)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Work Order Report Pipeline")
    parser.add_argument("--file", default=None, help="Process a single file (no archiving)")
    parser.add_argument("--mode", default="incremental", choices=["incremental", "full_refresh"])
    parser.add_argument("--source", default="file", choices=["file", "helix"], help="Use file or Helix API ingestion")
    parser.add_argument("--helix-period", default=None, choices=["today", "yesterday", "last-7-days"], help="Helix date period using HELIX_DATE_FIELD")
    parser.add_argument("--helix-start", default=None, help="Helix start date/datetime for HELIX_DATE_FIELD")
    parser.add_argument("--helix-end", default=None, help="Helix end date/datetime for HELIX_DATE_FIELD")
    parser.add_argument("--as-of", default=None, help="Override now() - YYYY-MM-DD HH:MM")
    args = parser.parse_args()

    run(
        mode=args.mode,
        file_arg=args.file,
        as_of_arg=getattr(args, "as_of"),
        source=args.source,
        helix_period=args.helix_period,
        helix_start=args.helix_start,
        helix_end=args.helix_end,
    )
