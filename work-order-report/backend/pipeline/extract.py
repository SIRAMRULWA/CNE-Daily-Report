"""
pipeline/extract.py
====================
Excel file discovery, extraction, and archiving.

Responsibilities:
  - Discover pending .xlsx / .xls files in the configured drop folder.
  - Open workbooks in read-only mode via openpyxl.
  - Detect the real header row by locating the Work Order ID column.
  - Map source column names to canonical WorkOrderRecord fields.
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

from helix.datetime_utils import parse_target_date
from helix.mapper import requester_name
from pipeline.models import WorkOrderRecord

logger = logging.getLogger(__name__)

BATCH_SIZE   = 500
ARCHIVE_DIR  = "archived"

# ---------------------------------------------------------------------------
# Column alias map — maps every known Excel / CSV header variant to the
# canonical field name used in WorkOrderRecord.
# ---------------------------------------------------------------------------
COLUMN_MAP = {
    # Identifier
    "workorderid":          "work_order_id",
    "workorder":            "work_order_id",
    "requestid":            "work_order_id",

    # Classification
    "workordertype":        "work_order_type",
    "categorizationtier1":  "category_tier1",
    "operationalcategorizationtier1": "category_tier1",

    # Descriptive
    "summary":              "summary",
    "status":               "status",
    "statusreason":         "status_reason",
    "priority":             "priority",
    "requester":            "requester",
    "customer":             "requester",
    "customerfirstname":    "requester_first_name",
    "customerlastname":     "requester_last_name",
    "supportgroupname":     "support_group",
    "supportgroup":         "support_group",
    "assigneegroup":        "support_group",
    "requestassignee":      "assignee",
    "assignee":             "assignee",
    "detaileddescription":  "notes",
    "notes":                "notes",

    # Timestamps
    "submitdate":           "submit_date",
    "createdate":           "submit_date",
    "scheduledenddate":     "target_date",
    "scheduledend":         "target_date",
    "requireddate":         "target_date",
    "daterequired":         "target_date",
    "targetdate":           "target_date",
    "completeddate":        "completed_date",
    "actualenddate":        "completed_date",
    "lastmodifieddate":     "last_modified",
}

_DATE_FORMATS = [
    "%m/%d/%Y, %I:%M:%S %p",
    "%m/%d/%Y %I:%M:%S %p",
    "%d/%m/%Y %H:%M",
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
    # Strip spaces, underscores and dashes so "Work Order ID", "Work_Order_ID"
    # and "WorkOrderID" all resolve to the same COLUMN_MAP key.
    key = name.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    return COLUMN_MAP.get(key, name.strip())


def _text(row_dict: dict, key: str) -> Optional[str]:
    return str(row_dict.get(key) or "").strip() or None


def _parse_target(value) -> Optional[datetime]:
    """Target dates follow the same date-only = end-of-day rule as Helix."""
    if isinstance(value, datetime) and value.time() == datetime.min.time():
        return parse_target_date(value.date())
    parsed = _parse_dt(value)
    if parsed is None:
        return parse_target_date(value)
    return parsed


def _row_to_record(row_dict: dict, source: str, raw: dict) -> Optional[WorkOrderRecord]:
    """Convert a normalised row dict to a WorkOrderRecord; None if the ID is missing."""
    work_order_id = _text(row_dict, "work_order_id")
    if not work_order_id:
        return None
    requester = _text(row_dict, "requester") or requester_name(
        row_dict.get("requester_first_name"), row_dict.get("requester_last_name")
    )
    return WorkOrderRecord(
        work_order_id   = work_order_id,
        summary         = _text(row_dict, "summary"),
        work_order_type = _text(row_dict, "work_order_type"),
        category_tier1  = _text(row_dict, "category_tier1"),
        status          = _text(row_dict, "status"),
        status_reason   = _text(row_dict, "status_reason"),
        priority        = _text(row_dict, "priority"),
        requester       = requester,
        support_group   = _text(row_dict, "support_group"),
        assignee        = _text(row_dict, "assignee"),
        notes           = _text(row_dict, "notes"),
        submit_date     = _parse_dt(row_dict.get("submit_date")),
        target_date     = _parse_target(row_dict.get("target_date")),
        completed_date  = _parse_dt(row_dict.get("completed_date")),
        last_modified   = _parse_dt(row_dict.get("last_modified")),
        source          = source,
        raw_payload     = {key: str(value) if value is not None else None for key, value in raw.items()},
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


def extract_file(filepath: str | Path) -> Generator[List[WorkOrderRecord], None, None]:
    """
    Yield batches of WorkOrderRecord from an Excel or CSV file.
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


def _extract_excel(filepath: Path) -> Generator[List[WorkOrderRecord], None, None]:
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

    # Find header row — scan up to 10 rows for the Work Order ID column
    headers = {}
    header_row_idx = None
    for i, row in enumerate(ws.iter_rows(max_row=10, values_only=True)):
        row_vals = [str(c).strip() if c is not None else "" for c in row]
        if any(_normalise_header(v) == "work_order_id" for v in row_vals if v):
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

    batch: List[WorkOrderRecord] = []
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


def _extract_csv(filepath: Path) -> Generator[List[WorkOrderRecord], None, None]:
    """Extract records from a CSV file."""
    with open(filepath, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        normalised_fieldnames = [_normalise_header(h) for h in (reader.fieldnames or [])]
        reader.fieldnames = normalised_fieldnames

        batch: List[WorkOrderRecord] = []
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
