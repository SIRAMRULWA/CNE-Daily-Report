"""
pipeline/transform.py
=====================
Business logic transformation engine.

This module applies the shared daily operations report logic:
  - report_group from Assignee Group patterns
  - report_category from Service Cat Tier 1, with dashboard-compatible fallback
    from RootRequestID, Summary, and Notes when Service Cat Tier 1 is blank
  - report inclusion from open statuses, named-assignee exclusions, and
    Work Order/PBI rules (Security work orders remain in scope)
  - category-specific SLA bands
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from config.mappings import (
    ASSIGN_TIME_BREACH_SECONDS,
    ASSIGN_TIME_NEARING_SECONDS,
    CATEGORY_MAP,
    CHANGE_NEARING_WINDOW_SECONDS,
    CHANGE_SCHEDULE_GRACE_SECONDS,
    CLOSED_STATUSES,
    EXCLUDED_ASSIGNEES,
    EXCLUDED_OPERATIONAL_CATEGORIES,
    EXCLUDED_REQUEST_PREFIXES,
    EXCLUDED_WORK_ORDER_GROUP_PATTERNS,
    OPEN_STATUSES,
    REQUEST_PREFIX_TASK_TYPE,
)
from pipeline.division_groups import load_group_patterns
from pipeline.models import ChangeRecord

logger = logging.getLogger(__name__)


def _classify_group(
    assignee_group: Optional[str],
    group_patterns: list[tuple[str, str]],
) -> Optional[str]:
    if not assignee_group:
        return None
    ag = assignee_group.strip()
    for pattern, label in group_patterns:
        if pattern.lower() in ag.lower():
            return label
    logger.debug("No group match for: %r", ag)
    return "Unknown"


def _op_cat_key(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def _text_key(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def _contains_security_indicator(rec: ChangeRecord) -> bool:
    summary = _text_key(rec.summary)
    notes = _text_key(rec.notes)

    return (
        summary.startswith("ARM:")
        or "PASSWORD" in summary
        or "ACCESS" in summary
        or "ARM:" in notes
        or "PASSWORD" in notes
        or "ACCESS" in notes
    )


def _infer_incident_task_type(rec: ChangeRecord) -> str:
    summary = _text_key(rec.summary)
    notes = _text_key(rec.notes)

    if _contains_security_indicator(rec):
        return "SECURITY"

    if summary.startswith("ALARM") or "ALARM" in notes:
        return "ALARM"

    return "FAULTS"


def derive_operational_category(rec: ChangeRecord) -> str:
    """Return the dashboard-compatible operational category for one record."""
    op_cat = _op_cat_key(rec.op_cat_tier1)
    if op_cat:
        if op_cat == "FAILURE":
            return "ALARM"
        return op_cat

    request_id = (rec.request_id or "").upper()
    if request_id.startswith("INC"):
        return _infer_incident_task_type(rec)

    for prefix, task_type in REQUEST_PREFIX_TASK_TYPE.items():
        if request_id.startswith(prefix):
            return task_type

    return "ALARM"


def _classify_category(rec: ChangeRecord) -> Optional[str]:
    task_type = derive_operational_category(rec)
    cat = CATEGORY_MAP.get(task_type)
    if cat:
        return cat

    logger.debug(
        "No category for %s (op_cat=%r task_type=%r)",
        rec.request_id,
        rec.op_cat_tier1,
        task_type,
    )
    return None


def _sla_status(rec: ChangeRecord, now: datetime) -> str:
    status = (rec.status or "").strip()
    if status in CLOSED_STATUSES:
        return "CLOSED"
    if status not in OPEN_STATUSES:
        return "OUT_OF_SCOPE"

    if rec.report_category == "CHANGE":
        if not rec.scheduled_end:
            return "NO_SCHEDULE"
        due = rec.scheduled_end + timedelta(seconds=CHANGE_SCHEDULE_GRACE_SECONDS)
        if now > due:
            return "BREACHED"
        if now > due - timedelta(seconds=CHANGE_NEARING_WINDOW_SECONDS):
            return "NEARING_SLA"
        return "WITHIN_SLA"

    if rec.report_category in ("INCIDENT", "ACCESS", "EVENT"):
        if not rec.assign_time:
            return "NO_ASSIGN_TIME"
        near_at = rec.assign_time + timedelta(seconds=ASSIGN_TIME_NEARING_SECONDS)
        due = rec.assign_time + timedelta(seconds=ASSIGN_TIME_BREACH_SECONDS)
        if now > due:
            return "BREACHED"
        if now >= near_at:
            return "NEARING_SLA"
        return "WITHIN_SLA"

    return "OUT_OF_SCOPE"


def _hours_open(rec: ChangeRecord, now: datetime) -> Optional[float]:
    if not rec.assign_time:
        return None
    status = (rec.status or "").strip()
    end = rec.closed_time if status in CLOSED_STATUSES and rec.closed_time else now
    return (end - rec.assign_time).total_seconds() / 3600.0


def _is_report_eligible(rec: ChangeRecord) -> bool:
    if rec.report_group in (None, "Unknown"):
        return False
    if rec.report_category not in ("INCIDENT", "CHANGE", "ACCESS", "EVENT"):
        return False

    if _text_key(rec.assignee) in EXCLUDED_ASSIGNEES:
        return False

    status = (rec.status or "").strip()
    if status not in OPEN_STATUSES:
        return False

    op_cat = _op_cat_key(rec.op_cat_tier1)
    request_id = (rec.request_id or "").upper()
    assignee_group = _text_key(rec.assignee_group)
    is_excluded_work_order_group = (
        request_id.startswith("WO")
        and any(
            pattern.upper() in assignee_group
            for pattern in EXCLUDED_WORK_ORDER_GROUP_PATTERNS
        )
    )
    if is_excluded_work_order_group:
        return False

    is_security_work_order = (
        request_id.startswith("WO")
        and rec.report_category == "ACCESS"
    )
    if op_cat in EXCLUDED_OPERATIONAL_CATEGORIES and not is_security_work_order:
        return False

    if (
        not is_security_work_order
        and any(request_id.startswith(prefix) for prefix in EXCLUDED_REQUEST_PREFIXES)
    ):
        return False

    return True


def transform_records(
    records: List[ChangeRecord],
    as_of: Optional[datetime] = None,
) -> List[ChangeRecord]:
    """
    Run all transformation stages in a single pass.
    Mutates records in-place and returns the same list.
    """
    now = as_of or datetime.now()
    group_patterns = load_group_patterns()

    stats = {
        "unknown_group": 0,
        "unknown_cat": 0,
        "breached": 0,
        "nearing": 0,
        "no_schedule": 0,
        "no_assign_time": 0,
        "excl_change": 0,
        "excl_incident": 0,
    }

    for rec in records:
        rec.report_group = _classify_group(rec.assignee_group, group_patterns)
        rec.report_category = _classify_category(rec)
        rec.sla_status = _sla_status(rec, now)
        rec.hours_open = _hours_open(rec, now)

        eligible = _is_report_eligible(rec)
        rec.exclude_change = False
        rec.exclude_incident = False
        if not eligible:
            if rec.report_category == "CHANGE":
                rec.exclude_change = True
            else:
                rec.exclude_incident = True

        if rec.report_group in (None, "Unknown"):
            stats["unknown_group"] += 1
        if rec.report_category is None:
            stats["unknown_cat"] += 1
        if rec.sla_status == "BREACHED":
            stats["breached"] += 1
        if rec.sla_status == "NEARING_SLA":
            stats["nearing"] += 1
        if rec.sla_status == "NO_SCHEDULE":
            stats["no_schedule"] += 1
        if rec.sla_status == "NO_ASSIGN_TIME":
            stats["no_assign_time"] += 1
        if rec.exclude_change:
            stats["excl_change"] += 1
        if rec.exclude_incident:
            stats["excl_incident"] += 1

    logger.info(
        "Transform complete | %d records | breached=%d nearing=%d no_sched=%d no_assign=%d "
        "excl_change=%d excl_incident=%d unknown_grp=%d unknown_cat=%d",
        len(records),
        stats["breached"],
        stats["nearing"],
        stats["no_schedule"],
        stats["no_assign_time"],
        stats["excl_change"],
        stats["excl_incident"],
        stats["unknown_group"],
        stats["unknown_cat"],
    )
    return records
