"""Unattended scheduler for Admin-configured real-time task reminders."""

import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from capabilities.task_reminders import get_task_reminder_service

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _scheduled_occurrence(subscription: dict, now: datetime) -> tuple[bool, str]:
    try:
        local_now = now.astimezone(ZoneInfo(subscription["timezone"]))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid reminder timezone: {subscription['timezone']}") from exc
    if _env_flag("TASK_REMINDER_WEEKDAYS_ONLY", True) and local_now.weekday() >= 5:
        return False, ""
    scheduled_at = datetime.combine(
        local_now.date(), subscription["send_time"], tzinfo=local_now.tzinfo
    )
    if local_now < scheduled_at:
        return False, ""
    if subscription["frequency"] == "WEEKLY" and local_now.weekday() != subscription["weekday"]:
        return False, ""

    # Only claim the occurrence near its configured time.  Treating every time
    # after send_time as due backfills today's occurrence when a subscription is
    # created or edited, which can send immediately and then again at a new time.
    interval_seconds = max(
        int(os.getenv("TASK_REMINDER_SCHEDULER_INTERVAL_SECONDS", "60")), 30
    )
    if local_now >= scheduled_at + timedelta(seconds=interval_seconds * 2):
        return False, ""

    # A configuration cannot be due for an occurrence that predates that
    # configuration version.  Both create and update endpoints maintain these
    # timestamps in PostgreSQL.
    effective_at = subscription.get("updated_at") or subscription.get("created_at")
    if effective_at is not None:
        if effective_at.tzinfo is None:
            effective_at = effective_at.replace(tzinfo=ZoneInfo("UTC"))
        if effective_at.astimezone(local_now.tzinfo) > scheduled_at:
            return False, ""

    slot = f"scheduled-{local_now.date().isoformat()}-{subscription['send_time'].strftime('%H%M')}"
    return True, slot


def run_due(now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(ZoneInfo("UTC"))
    counts = {"due": 0, "sent": 0, "failed": 0, "already_processed": 0}
    if not _env_flag("TASK_REMINDER_AUTOMATION_APPROVED", False):
        logger.info("Automatic task reminders are disabled pending approval")
        return counts
    service = get_task_reminder_service()
    subscriptions = service.list_enabled_subscriptions()
    for subscription in subscriptions:
        try:
            due, idempotency_key = _scheduled_occurrence(subscription, now)
            if not due:
                continue
            counts["due"] += 1
            result = service.execute(
                subscription["id"], idempotency_key, "AUTOMATION", "automated-reminder-scheduler"
            )
            if result.get("duplicate"):
                counts["already_processed"] += 1
            elif result.get("status") == "SENT":
                counts["sent"] += 1
            else:
                counts["failed"] += 1
        except Exception:
            logger.exception("Could not process reminder subscription %s", subscription.get("id"))
            counts["failed"] += 1
    logger.info("Automated task reminder run: %s", counts)
    return counts
