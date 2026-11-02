"""Unattended scheduler for configured Daily Report email subscriptions."""

import argparse
import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pipeline.db import get_cursor, run_query
from capabilities.daily_reports import email_closed_changes
from notifications.reports import attachment, html_body, report_data
from notifications.transport import configured_transport

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_due(subscription: dict, now: datetime) -> tuple[bool, date]:
    try:
        local_now = now.astimezone(ZoneInfo(subscription["timezone"]))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid subscription timezone: {subscription['timezone']}") from exc
    if _env_flag("REPORT_EMAIL_WEEKDAYS_ONLY", True) and local_now.weekday() >= 5:
        return False, local_now.date()
    scheduled_at = datetime.combine(
        local_now.date(), subscription["send_time"], tzinfo=local_now.tzinfo
    )
    if local_now < scheduled_at:
        return False, local_now.date()
    if subscription["frequency"] == "WEEKLY" and local_now.weekday() != subscription["weekday"]:
        return False, local_now.date()

    # Evaluate only the current polling window. Without an upper bound, a
    # subscription created or rescheduled after its send time is incorrectly
    # treated as an overdue occurrence and sends immediately.
    interval_seconds = max(
        int(os.getenv("REPORT_EMAIL_SCHEDULER_INTERVAL_SECONDS", "60")), 30
    )
    if local_now >= scheduled_at + timedelta(seconds=interval_seconds * 2):
        return False, local_now.date()

    # Do not backfill an occurrence which predates this configuration version.
    effective_at = subscription.get("updated_at") or subscription.get("created_at")
    if effective_at is not None:
        if effective_at.tzinfo is None:
            effective_at = effective_at.replace(tzinfo=ZoneInfo("UTC"))
        if effective_at.astimezone(local_now.tzinfo) > scheduled_at:
            return False, local_now.date()

    return True, local_now.date()


def _claim(subscription_id: int, report_date: date) -> dict | None:
    retry_minutes = max(int(os.getenv("REPORT_EMAIL_RETRY_MINUTES", "15")), 1)
    max_attempts = max(int(os.getenv("REPORT_EMAIL_MAX_ATTEMPTS", "5")), 1)
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO reporting.report_email_deliveries
                (subscription_id, report_date, status)
            VALUES (%s, %s, 'SENDING')
            ON CONFLICT (subscription_id, report_date) DO UPDATE SET
                status = 'SENDING', attempt_count = reporting.report_email_deliveries.attempt_count + 1,
                started_at = NOW(), completed_at = NULL, error_message = NULL
            WHERE (reporting.report_email_deliveries.status = 'SKIPPED'
                   OR (reporting.report_email_deliveries.status = 'FAILED'
                       AND reporting.report_email_deliveries.attempt_count < %s))
              AND reporting.report_email_deliveries.started_at <= NOW() - (%s * INTERVAL '1 minute')
            RETURNING *
            """,
            (subscription_id, report_date, max_attempts, retry_minutes),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _finish(delivery_id: int, status: str, recipients: list[str], record_count: int = 0,
            provider: str | None = None, message_id: str | None = None, error: str | None = None) -> None:
    with get_cursor() as cur:
        cur.execute(
            """UPDATE reporting.report_email_deliveries
               SET status=%s, recipients=%s::jsonb, record_count=%s, provider=%s,
                   provider_message_id=%s, error_message=%s, completed_at=NOW()
               WHERE id=%s""",
            (status, __import__("json").dumps(recipients), record_count, provider, message_id, error, delivery_id),
        )


def send_subscription(subscription: dict, report_date: date, force: bool = False) -> str:
    delivery = _claim(subscription["id"], report_date)
    if not delivery:
        return "already_processed"
    recipients = list(subscription["recipients"] or [])
    cc = list(subscription["cc_recipients"] or [])
    try:
        heartbeat = run_query(
            "SELECT last_run_at, last_run_status FROM reporting.pipeline_heartbeat WHERE id=1"
        )
        if not force and (
            not heartbeat
            or heartbeat[0]["last_run_status"] != "SUCCESS"
            or heartbeat[0]["last_run_at"] is None
            or heartbeat[0]["last_run_at"].astimezone(ZoneInfo(subscription["timezone"])).date() != report_date
        ):
            _finish(delivery["id"], "SKIPPED", recipients + cc, error="A fresh successful pipeline run is not available")
            return "skipped"
        summary, records = report_data(report_date, subscription["division"], subscription["assignee_group"])
        if not summary:
            _finish(delivery["id"], "SKIPPED", recipients + cc, error="No report snapshot exists for this scope/date")
            return "skipped"
        transport = configured_transport()
        closed_changes = email_closed_changes(
            report_date, subscription["division"], subscription["assignee_group"]
        )
        report_attachment = attachment(
            records, subscription["division"], report_date,
            subscription["attachment_format"], closed_changes,
        )
        subject_scope = subscription["assignee_group"] or subscription["division"]
        message_id = transport.send(
            recipients,
            cc,
            f"Daily Report - {subject_scope} - {report_date.isoformat()}",
            html_body(
                subscription["name"], report_date, subscription["division"],
                subscription["assignee_group"], summary, len(records),
                subscription["attachment_format"],
            ),
            report_attachment,
        )
        _finish(delivery["id"], "SENT", recipients + cc, len(records), transport.provider, message_id)
        return "sent"
    except Exception as exc:
        logger.exception("Report email subscription %s failed", subscription["id"])
        _finish(delivery["id"], "FAILED", recipients + cc, error=str(exc)[:2000])
        return "failed"


def run_due(now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(ZoneInfo("UTC"))
    approved = _env_flag("REPORT_EMAIL_AUTOMATION_APPROVED", False)
    if not approved:
        logger.info("Automatic report email delivery is disabled pending approval")
        return {"due": 0, "sent": 0, "skipped": 0, "failed": 0, "already_processed": 0}
    subscriptions = run_query("SELECT * FROM config.report_email_subscriptions WHERE enabled AND NOT deleted ORDER BY id")
    counts = {"due": 0, "sent": 0, "skipped": 0, "failed": 0, "already_processed": 0}
    for subscription in subscriptions:
        try:
            due, report_date = _is_due(subscription, now)
            if not due:
                continue
            counts["due"] += 1
            result = send_subscription(subscription, report_date)
            counts[result] += 1
        except Exception:
            logger.exception("Could not process report subscription %s", subscription.get("id"))
            counts["failed"] += 1
    logger.info("Automated report email run: %s", counts)
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = run_due()
    raise SystemExit(1 if result["failed"] else 0)
