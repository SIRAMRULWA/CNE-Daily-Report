"""Real-time Helix outstanding-task reminder generation and delivery."""

import logging
import os
from collections import defaultdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser
from helix.extractor import WORKSPACE_TIMEZONE
from notifications.reports import attachment as daily_report_attachment, reminder_html_body
from notifications.transport import Attachment
from pipeline.models import ChangeRecord
from pipeline.transform import transform_records

logger = logging.getLogger(__name__)

def _datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(
            value / 1000 if value > 10_000_000_000 else value,
            tz=ZoneInfo(WORKSPACE_TIMEZONE),
        )
    else:
        try:
            parsed = date_parser.parse(str(value))
        except (TypeError, ValueError, OverflowError):
            return None
    workspace_zone = ZoneInfo(WORKSPACE_TIMEZONE)
    return (
        parsed.replace(tzinfo=workspace_zone)
        if parsed.tzinfo is None
        else parsed.astimezone(workspace_zone)
    )


def _prepare(rows: list[dict], now: datetime) -> list[dict]:
    stale_days = max(int(os.getenv("TASK_REMINDER_STALE_DAYS", "7")), 1)
    prepared = []
    for source in rows:
        row = dict(source)
        created = _datetime(row.get("create_date"))
        age_days = max((now - created).days, 0) if created else None
        reasons = []
        priority = str(row.get("priority") or "").strip().upper()
        if priority in {"CRITICAL", "HIGH", "1-CRITICAL", "2-HIGH"}:
            reasons.append("High priority")
        if not str(row.get("assignee") or "").strip():
            reasons.append("Unassigned")
        if age_days is not None and age_days >= stale_days:
            reasons.append(f"Open {age_days} days")
        if str(row.get("status") or "").strip().lower() == "pending":
            reasons.append("Pending")
        sla_status = str(row.get("sla_status") or "")
        if sla_status == "BREACHED":
            reasons.append("SLA breached")
        elif sla_status == "NEARING_SLA":
            reasons.append("Nearing SLA")
        elif sla_status == "NO_SCHEDULE":
            reasons.append("No schedule")
        elif sla_status == "NO_ASSIGN_TIME":
            reasons.append("No assign time")
        row["age_days"] = age_days
        row["attention"] = ", ".join(reasons) if reasons else "Continue progress and close when complete"
        row["requires_attention"] = bool(reasons)
        prepared.append(row)
    return sorted(
        prepared,
        key=lambda row: (
            {"BREACHED": 0, "NEARING_SLA": 1}.get(str(row.get("sla_status") or ""), 2),
            -(row.get("age_days") or 0),
            str(row.get("assignee_group") or ""),
            str(row.get("request_id") or ""),
        ),
    )


def _daily_report_rows(records: list[ChangeRecord], division: str, assignee_group: str | None,
                       now: datetime) -> list[dict]:
    """Apply the shared Daily Report transformations to canonical live records."""
    transform_records(
        records,
        as_of=now.astimezone(ZoneInfo(WORKSPACE_TIMEZONE)).replace(tzinfo=None),
    )
    eligible = [
        record for record in records
        if not record.is_excluded
        and record.report_group == division
        and (assignee_group is None or record.assignee_group == assignee_group)
    ]
    return [
        {
            "request_id": record.request_id,
            "task_id": record.task_id,
            "report_category": record.report_category,
            "op_cat_tier1": record.op_cat_tier1,
            "priority": record.priority,
            "status": record.status,
            "status_reason": record.status_reason,
            "assignee_group": record.assignee_group,
            "assignee": record.assignee,
            "summary": record.summary,
            "create_date": record.create_date,
            "assign_time": record.assign_time,
            "scheduled_start": record.scheduled_start,
            "scheduled_end": record.scheduled_end,
            "sla_status": record.sla_status,
            "hours_open": record.hours_open,
        }
        for record in eligible
    ]


def _excel(rows: list[dict], division: str, generated_at: datetime) -> Attachment:
    """Build the reminder file with the exact Daily Report XLSX generator."""
    sla_order = {
        "BREACHED": 0, "NEARING_SLA": 1, "NO_SCHEDULE": 2,
        "NO_ASSIGN_TIME": 3, "WITHIN_SLA": 4,
    }
    ordered = sorted(
        rows,
        key=lambda row: (
            sla_order.get(str(row.get("sla_status") or ""), 9),
            str(row.get("assignee_group") or "").casefold(),
            str(row.get("request_id") or ""),
            str(row.get("task_id") or ""),
        ),
    )
    return daily_report_attachment(ordered, division, generated_at.date(), "XLSX")


def _live_summary(rows: list[dict]) -> list[dict]:
    """Aggregate live records into the same bands and categories as Daily Reports."""
    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"incident_count": 0, "change_count": 0, "access_count": 0, "event_count": 0}
    )
    for row in rows:
        group = str(row.get("assignee_group") or "Unassigned")
        category = str(row.get("report_category") or "").upper()
        for band in (
            "Total Open Calls",
            "Calls Nearing SLA" if row.get("sla_status") == "NEARING_SLA" else None,
            "Breached Calls" if row.get("sla_status") == "BREACHED" else None,
        ):
            if band and category in {"INCIDENT", "CHANGE", "ACCESS", "EVENT"}:
                counts[(group, band)][f"{category.lower()}_count"] += 1

    summary = []
    band_order = {"Total Open Calls": 0, "Calls Nearing SLA": 1, "Breached Calls": 2}
    for (group, band), category_counts in counts.items():
        summary.append({
            "assignee_group": group,
            "sla_band": band,
            **category_counts,
            "total_count": sum(category_counts.values()),
        })
    return sorted(summary, key=lambda row: (row["assignee_group"], band_order[row["sla_band"]]))


def _html(subscription: dict, rows: list[dict], generated_at: datetime) -> str:
    oldest_days = max((int(row.get("age_days") or 0) for row in rows), default=0)
    return reminder_html_body(
        generated_at,
        subscription["division"],
        subscription.get("assignee_group"),
        _live_summary(rows),
        len(rows),
        oldest_days,
    )


def execute(
    subscription_id: int,
    idempotency_key: str,
    trigger_source: str,
    requested_by: str,
    request=None,
) -> dict:
    """Compatibility entrypoint delegating to the Task Reminder capability."""
    from capabilities.task_reminders import get_task_reminder_service
    from capabilities.task_reminders.errors import (
        TaskReminderConflictError,
        TaskReminderNotFoundError,
    )

    try:
        return get_task_reminder_service().execute(
            subscription_id,
            idempotency_key,
            trigger_source,
            requested_by,
            request=request,
        )
    except TaskReminderNotFoundError as exc:
        raise LookupError(str(exc)) from exc
    except TaskReminderConflictError as exc:
        raise PermissionError(str(exc)) from exc
