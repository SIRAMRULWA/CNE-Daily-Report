"""
pipeline/extract.py
====================
Excel file discovery, extraction, and archiving.

Responsibilities:
  - Discover pending .xlsx / .xls files in the configured drop folder.
  - Open workbooks in read-only mode via openpyxl.
  - Detect the real header row by locating 'Request ID'.
  - Map source column names to canonical ChangeRecord fields.
  - Yield records in batches of BATCH_SIZE.
  - Archive successfully processed files.

Also handles CSV files (same column structure, different file type) so the
pipeline can run from both the FTP CSV drop and the Excel manual export.
"""

import csv
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

import openpyxl

from pipeline.models import ChangeRecord

logger = logging.getLogger(__name__)

BATCH_SIZE   = 500
ARCHIVE_DIR  = "archived"

# ---------------------------------------------------------------------------
# Column alias map — maps every known Excel / CSV header variant to the
# canonical field name used in ChangeRecord.
# ---------------------------------------------------------------------------
COLUMN_MAP = {
    # Request / Task ID
    "request id":           "request_id",
    "requestid":            "request_id",
    "task id":              "task_id",
    "taskid":               "task_id",

    # Operational category — all known header spellings
    "op cat tier 1":        "op_cat_tier1",
    "opcattier1":           "op_cat_tier1",
    "service cat tier 1":   "op_cat_tier1",
    "servicecattier1":      "op_cat_tier1",

    # Descriptive
    "summary":              "summary",
    "assignee":             "assignee",
    "priority":             "priority",
    "status":               "status",

    # Timestamps — all real-data header variants observed
    "create date":          "create_date",
    "createdate":           "create_date",
    "assign time":          "assign_time",
    "assigntime":           "assign_time",

    # Closed/actual end — "ClosedDate" is the CSV export header,
    # "Closed Date" and "Actual End Date" appear in Excel exports
    "closed date":          "closed_time",
    "closeddate":           "closed_time",
    "actual end date":      "closed_time",
    "actualenddate":        "closed_time",

    # Scheduled start
    "scheduled start date": "scheduled_start",
    "scheduledstart":       "scheduled_start",
    "scheduledstartdate":   "scheduled_start",

    # Scheduled end — CRITICAL: real CSV exports use "ScheduledEnd" (no underscore/space),
    # Excel exports use "Scheduled End Date". Both must map correctly.
    "scheduled end date":   "scheduled_end",
    "scheduledenddate":     "scheduled_end",
    "scheduled_end":        "scheduled_end",   # underscore variant
    "scheduledend":         "scheduled_end",   # ← real CSV export header (no space/underscore)

    # Status reason
    "status reason":        "status_reason",
    "statusreason":         "status_reason",
    "statusreasonselection":"status_reason",

    # Assignee group
    "assignee group":       "assignee_group",
    "assigneegroup":        "assignee_group",

    # Notes
    "notes":                "notes",
}

_DATE_FORMATS = [
    "%m/%d/%Y, %I:%M:%S %p",
    "%m/%d/%Y, %I:%M:%S.%f %p",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
]


def _parse_dt(value) -> Optional[datetime]:
    """Parse a datetime from string or Excel serial. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    logger.debug("Could not parse datetime: %r", raw)
    return None


def _normalise_header(name: str) -> str:
    # Strip spaces and underscores so "ScheduledEnd", "Scheduled_End",
    # "Scheduled End Date" all resolve to the same COLUMN_MAP key.
    key = name.strip().lower().replace(" ", "").replace("_", "")
    return COLUMN_MAP.get(key, name.strip())


def _row_to_record(row_dict: dict, source: str, raw: dict) -> Optional[ChangeRecord]:
    """Convert a normalised row dict to a ChangeRecord. Returns None if request_id is missing."""
    rid = str(row_dict.get("request_id") or "").strip()
    tid = str(row_dict.get("task_id") or "").strip()
    if not rid:
        return None
    return ChangeRecord(
        request_id      = rid,
        task_id         = tid,
        op_cat_tier1    = str(row_dict.get("op_cat_tier1") or "").strip() or None,
        summary         = str(row_dict.get("summary") or "").strip() or None,
        assignee        = str(row_dict.get("assignee") or "").strip() or None,
        priority        = str(row_dict.get("priority") or "").strip() or None,
        status          = str(row_dict.get("status") or "").strip() or None,
        status_reason   = str(row_dict.get("status_reason") or "").strip() or None,
        assignee_group  = str(row_dict.get("assignee_group") or "").strip() or None,
        notes           = str(row_dict.get("notes") or "").strip() or None,
        create_date     = _parse_dt(row_dict.get("create_date")),
        assign_time     = _parse_dt(row_dict.get("assign_time")),
        closed_time     = _parse_dt(row_dict.get("closed_time")),
        scheduled_start = _parse_dt(row_dict.get("scheduled_start")),
        scheduled_end   = _parse_dt(row_dict.get("scheduled_end")),
        source          = source,
        raw_payload     = raw,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_pending_files(drop_dir: str | Path) -> List[Path]:
    """Return all .xlsx, .xls, and .csv files in drop_dir (not in archived/)."""
    drop_dir = Path(drop_dir)
    if not drop_dir.exists():
        logger.warning("Drop directory does not exist: %s", drop_dir)
        return []
    files = [
        f for f in drop_dir.iterdir()
        if f.is_file() and f.suffix.lower() in (".xlsx", ".xls", ".csv")
        and f.parent.name != ARCHIVE_DIR
    ]
    logger.info("Found %d pending file(s) in %s", len(files), drop_dir)
    return sorted(files)


def extract_file(filepath: str | Path) -> Generator[List[ChangeRecord], None, None]:
    """
    Yield batches of ChangeRecord from an Excel or CSV file.
    Each batch is at most BATCH_SIZE records.
    """
    filepath = Path(filepath)
    suffix = filepath.suffix.lower()

    if suffix in (".xlsx", ".xls"):
        yield from _extract_excel(filepath)
    elif suffix == ".csv":
        yield from _extract_csv(filepath)
    else:
        logger.warning("Unsupported file type: %s", suffix)


def _extract_excel(filepath: Path) -> Generator[List[ChangeRecord], None, None]:
    """Extract records from an Excel workbook."""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)

    # Use first visible sheet
    ws = None
    for sheet in wb.worksheets:
        if sheet.sheet_state == "visible":
            ws = sheet
            break
    if ws is None:
        logger.error("No visible sheet in %s", filepath.name)
        wb.close()
        return

    # Find header row — scan up to 10 rows for 'Request ID'
    headers = {}
    header_row_idx = None
    for i, row in enumerate(ws.iter_rows(max_row=10, values_only=True)):
        row_vals = [str(c).strip() if c is not None else "" for c in row]
        if any("request id" in v.lower() or "requestid" in v.lower() for v in row_vals):
            headers = {
                _normalise_header(v): idx
                for idx, v in enumerate(row_vals)
                if v
            }
            header_row_idx = i
            break

    if not headers:
        logger.error("Could not find header row in %s", filepath.name)
        wb.close()
        return

    logger.info("Header row at row %d in %s", (header_row_idx or 0) + 1, filepath.name)

    batch: List[ChangeRecord] = []
    for row in ws.iter_rows(min_row=(header_row_idx or 0) + 2, values_only=True):
        raw = {k: row[v] for k, v in headers.items() if v < len(row)}
        rec = _row_to_record(raw, source="excel", raw=raw)
        if rec:
            batch.append(rec)
        if len(batch) >= BATCH_SIZE:
            yield batch
            batch = []

    if batch:
        yield batch

    wb.close()
    logger.info("Extracted records from %s", filepath.name)


def _extract_csv(filepath: Path) -> Generator[List[ChangeRecord], None, None]:
    """Extract records from a CSV file."""
    with open(filepath, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        normalised_fieldnames = [_normalise_header(h) for h in (reader.fieldnames or [])]
        reader.fieldnames = normalised_fieldnames

        batch: List[ChangeRecord] = []
        for row in reader:
            raw = dict(row)
            rec = _row_to_record(raw, source="csv", raw=raw)
            if rec:
                batch.append(rec)
            if len(batch) >= BATCH_SIZE:
                yield batch
                batch = []

        if batch:
            yield batch

    logger.info("Extracted records from %s", filepath.name)


def archive_file(filepath: str | Path) -> None:
    """Move a processed file to the archived/ subdirectory."""
    filepath = Path(filepath)
    archive_dir = filepath.parent / ARCHIVE_DIR
    archive_dir.mkdir(exist_ok=True)

    # Timestamp the archived copy to avoid collisions
    stamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = archive_dir / f"{filepath.stem}_{stamp}{filepath.suffix}"
    shutil.move(str(filepath), str(target))
    logger.info("Archived %s → %s", filepath.name, target.name)
