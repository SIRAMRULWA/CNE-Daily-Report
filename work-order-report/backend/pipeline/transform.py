"""
pipeline/transform.py
=====================
Work Order business-rule transformation.

Every Work Order passes through this one transform, so the report, the
current-records view and the custom Helix report all agree. Stages:

  1. division        support group -> division (database mappings)
  2. report_category Work Order Type, else Categorization Tier 1, else Unclassified
  3. sla_status      target-date rule (see _sla_status)
  4. hours_open      submit date -> now (open) or -> completed date (closed)
  5. days_to_target  whole days until the target date; negative = overdue
  6. is_open         status is one of the open statuses
  7. is_excluded     outside the report scope (see is_report_eligible)
"""

import logging
import math
from datetime import datetime, timedelta
from typing import List, Optional

from config.mappings import (
    CLOSED_STATUSES,
    GRACE_MINUTES,
    NEARING_WINDOW_HOURS,
    OPEN_STATUSES,
    UNCLASSIFIED_CATEGORY,
)
from pipeline.division_groups import load_group_patterns
from pipeline.models import WorkOrderRecord

logger = logging.getLogger(__name__)

UNKNOWN_DIVISION = "Unknown"


def _status(rec: WorkOrderRecord) -> str:
    return (rec.status or "").strip()


def classify_division(
    support_group: Optional[str],
    group_patterns: list[tuple[str, str]],
) -> Optional[str]:
    """Match a support group to a division; longest (most specific) pattern wins."""
    if not support_group:
        return None
    group = support_group.strip().lower()
    for pattern, division in sorted(group_patterns, key=lambda item: -len(item[0])):
        if pattern.strip().lower() in group:
            return division
    logger.debug("No division match for support group %r", support_group)
    return UNKNOWN_DIVISION


def classify_category(rec: WorkOrderRecord) -> str:
    for value in (rec.work_order_type, rec.category_tier1):
        text = (value or "").strip()
        if text:
            return text
    return UNCLASSIFIED_CATEGORY


def due_at(rec: WorkOrderRecord) -> Optional[datetime]:
    """The moment a Work Order becomes late (target date plus any grace)."""
    if rec.target_date is None:
        return None
    return rec.target_date + timedelta(minutes=GRACE_MINUTES)


def sla_status(rec: WorkOrderRecord, now: datetime) -> str:
    """Return the SLA status for one Work Order.

    Open Work Orders:
        BREACHED        now > target
        NEARING_SLA     target - nearing window < now <= target
        WITHIN_SLA      now <= target - nearing window
        NO_TARGET_DATE  no target date
    Completed Work Orders:
        MET_TARGET      completed on or before target
        MISSED_TARGET   completed after target
        NO_TARGET_DATE  no target date
    Anything else (Cancelled, Rejected, Draft, unknown) is OUT_OF_SCOPE.
    """
    status = _status(rec)
    due = due_at(rec)

    if status in OPEN_STATUSES:
        if due is None:
            return "NO_TARGET_DATE"
        if now > due:
            return "BREACHED"
        if now > due - timedelta(hours=NEARING_WINDOW_HOURS):
            return "NEARING_SLA"
        return "WITHIN_SLA"

    if status in CLOSED_STATUSES:
        if due is None:
            return "NO_TARGET_DATE"
        completed = rec.completed_date
        if completed is None:
            return "MISSED_TARGET" if now > due else "MET_TARGET"
        return "MET_TARGET" if completed <= due else "MISSED_TARGET"

    return "OUT_OF_SCOPE"


def hours_open(rec: WorkOrderRecord, now: datetime) -> Optional[float]:
    if rec.submit_date is None:
        return None
    end = now
    if _status(rec) in CLOSED_STATUSES and rec.completed_date is not None:
        end = rec.completed_date
    return max((end - rec.submit_date).total_seconds(), 0) / 3600.0


def days_to_target(rec: WorkOrderRecord, now: datetime) -> Optional[int]:
    """Whole days until the target date; negative when overdue (rounded away from 0)."""
    due = due_at(rec)
    if due is None:
        return None
    if _status(rec) in CLOSED_STATUSES and rec.completed_date is not None:
        reference = rec.completed_date
    else:
        reference = now
    days = (due - reference).total_seconds() / 86_400
    return math.floor(days) if days >= 0 else -math.ceil(-days)


def is_report_eligible(rec: WorkOrderRecord) -> bool:
    """In scope = mapped division, and an open or completed status."""
    if rec.division in (None, UNKNOWN_DIVISION):
        return False
    status = _status(rec)
    return status in OPEN_STATUSES or status in CLOSED_STATUSES


def transform_records(
    records: List[WorkOrderRecord],
    as_of: Optional[datetime] = None,
    group_patterns: Optional[list[tuple[str, str]]] = None,
) -> List[WorkOrderRecord]:
    """Apply every stage in one pass. Mutates records in place and returns them."""
    now = as_of or datetime.now()
    patterns = load_group_patterns() if group_patterns is None else group_patterns
    counts: dict[str, int] = {}

    for rec in records:
        rec.division = classify_division(rec.support_group, patterns)
        rec.report_category = classify_category(rec)
        rec.sla_status = sla_status(rec, now)
        rec.hours_open = hours_open(rec, now)
        rec.days_to_target = days_to_target(rec, now)
        rec.is_open = _status(rec) in OPEN_STATUSES
        rec.is_excluded = not is_report_eligible(rec)

        key = "EXCLUDED" if rec.is_excluded else rec.sla_status
        counts[key] = counts.get(key, 0) + 1

    logger.info(
        "Transform complete | %d Work Orders | %s",
        len(records),
        " ".join(f"{key.lower()}={value}" for key, value in sorted(counts.items())),
    )
    return records
