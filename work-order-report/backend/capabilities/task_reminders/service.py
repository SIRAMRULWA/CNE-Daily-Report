"""Application service for Task Reminder configuration and execution."""

from __future__ import annotations

import logging
from typing import Protocol

from app_core.audit import audit_event
from app_core.clock import workspace_now
from app_core.recipients import RecipientPolicyError, validate_recipient_domains
from capabilities.organization import get_organization_service
from capabilities.task_reminders.errors import (
    TaskReminderConflictError,
    TaskReminderExecutionError,
    TaskReminderNotFoundError,
    TaskReminderValidationError,
)
from config.mappings import OPEN_STATUSES
from helix.extractor import HelixExtractor
from notifications.transport import configured_transport

logger = logging.getLogger(__name__)


class TaskReminderStore(Protocol):
    def list_subscriptions(self, limit: int, offset: int) -> list[dict]: ...
    def list_enabled_subscriptions(self) -> list[dict]: ...
    def get_subscription(self, subscription_id: int) -> dict | None: ...
    def create_subscription(self, values: dict, actor: str) -> dict: ...
    def replace_subscription(
        self, subscription_id: int, values: dict, actor: str
    ) -> dict | None: ...
    def set_enabled(
        self, subscription_id: int, enabled: bool, actor: str
    ) -> dict | None: ...
    def soft_delete(self, subscription_id: int, actor: str) -> bool: ...
    def list_executions(
        self, subscription_id: int | None, status: str | None,
        limit: int, offset: int,
    ) -> list[dict]: ...
    def claim_execution(
        self, subscription_id: int, idempotency_key: str, trigger_source: str,
        recipients: list[str], requested_by: str,
    ) -> tuple[dict, bool]: ...
    def complete_execution(
        self, execution_id: int, record_count: int, attention_count: int,
        provider: str, message_id: str | None,
    ) -> dict: ...
    def fail_execution(
        self, execution_id: int, error_code: str, error_message: str
    ) -> None: ...


class TaskReminderService:
    def __init__(self, repository: TaskReminderStore):
        self.repository = repository

    def list_subscriptions(self, limit: int, offset: int) -> list[dict]:
        return self.repository.list_subscriptions(limit, offset)

    def list_enabled_subscriptions(self) -> list[dict]:
        return self.repository.list_enabled_subscriptions()

    def create_subscription(
        self, values: dict, actor: str, request=None
    ) -> dict:
        self._validate_configuration(values)
        row = self.repository.create_subscription(values, actor)
        audit_event(
            "create_task_reminder_subscription", "task_reminder_subscription",
            str(row["id"]), actor,
            {
                "division": values["division"],
                "assignee_group": values.get("assignee_group"),
                "enabled": values["enabled"],
                "recipient_count": len(values["recipients"]),
            },
            request=request,
        )
        return row

    def replace_subscription(
        self, subscription_id: int, values: dict, actor: str, request=None
    ) -> dict:
        self._validate_configuration(values)
        row = self.repository.replace_subscription(subscription_id, values, actor)
        if row is None:
            raise TaskReminderNotFoundError("Reminder subscription not found")
        audit_event(
            "replace_task_reminder_subscription", "task_reminder_subscription",
            str(subscription_id), actor,
            {"division": values["division"], "enabled": values["enabled"]},
            request=request,
        )
        return row

    def set_enabled(
        self, subscription_id: int, enabled: bool, actor: str, request=None
    ) -> dict:
        row = self.repository.set_enabled(subscription_id, enabled, actor)
        if row is None:
            raise TaskReminderNotFoundError("Reminder subscription not found")
        audit_event(
            "update_task_reminder_subscription", "task_reminder_subscription",
            str(subscription_id), actor, {"enabled": enabled}, request=request,
        )
        return row

    def delete_subscription(
        self, subscription_id: int, actor: str, request=None
    ) -> dict:
        if not self.repository.soft_delete(subscription_id, actor):
            raise TaskReminderNotFoundError("Reminder subscription not found")
        audit_event(
            "delete_task_reminder_subscription", "task_reminder_subscription",
            str(subscription_id), actor, request=request,
        )
        return {"id": subscription_id, "deleted": True}

    def list_executions(
        self, subscription_id: int | None, status: str | None,
        limit: int, offset: int,
    ) -> list[dict]:
        return self.repository.list_executions(
            subscription_id, status, limit, offset
        )

    def execute(
        self, subscription_id: int, idempotency_key: str, trigger_source: str,
        requested_by: str, request=None,
    ) -> dict:
        # Imported lazily so the established renderer helpers remain usable
        # without creating a module-import cycle through the compatibility API.
        from notifications.task_reminders import (
            _daily_report_rows,
            _excel,
            _html,
            _prepare,
        )

        subscription = self.repository.get_subscription(subscription_id)
        if subscription is None:
            raise TaskReminderNotFoundError("Reminder subscription not found")
        if not subscription["enabled"]:
            raise TaskReminderConflictError("Reminder subscription is disabled")

        recipients = list(subscription["recipients"] or [])
        cc = list(subscription["cc_recipients"] or [])
        execution, duplicate = self.repository.claim_execution(
            subscription_id, idempotency_key, trigger_source,
            recipients + cc, requested_by,
        )
        if duplicate:
            return {**execution, "duplicate": True}

        try:
            groups = [
                row["assignee_group"]
                for row in get_organization_service().list_groups(
                    subscription["division"]
                )
            ]
            if subscription.get("assignee_group"):
                groups = [subscription["assignee_group"]]
            if not groups:
                raise ValueError(
                    "No active assignee groups are configured for the reminder scope"
                )

            extractor = HelixExtractor()
            if not extractor.is_configured():
                raise RuntimeError("Helix connection is not configured")
            configured_limit = int(subscription["max_records"])
            records = [
                record
                for batch in extractor.extract_changes(
                    assignee_groups=groups,
                    statuses=sorted(OPEN_STATUSES),
                    max_records=configured_limit + 1,
                    include_successful_closures=False,
                )
                for record in batch
            ]
            if len(records) > configured_limit:
                raise RuntimeError(
                    "Live Helix result exceeds the configured max_records "
                    f"limit ({configured_limit}); no partial reminder was sent"
                )

            now = workspace_now()
            report_rows = _daily_report_rows(
                records, subscription["division"],
                subscription.get("assignee_group"), now,
            )
            rows = _prepare(report_rows, now)
            attention_count = sum(
                1 for row in rows if row["requires_attention"]
            )
            transport = configured_transport()
            scope = (
                subscription.get("assignee_group") or subscription["division"]
            )
            message_id = transport.send(
                recipients,
                cc,
                subscription.get("subject")
                or f"Action Required: {len(rows)} Open Tasks - {scope}",
                _html(subscription, rows, now),
                _excel(rows, subscription["division"], now),
            )
            result = self.repository.complete_execution(
                execution["id"], len(rows), attention_count,
                transport.provider, message_id,
            )
            audit_event(
                "send_task_reminder", "task_reminder_execution",
                str(execution["id"]), requested_by,
                {
                    "subscription_id": subscription_id,
                    "division": subscription["division"],
                    "assignee_group": subscription.get("assignee_group"),
                    "record_count": len(rows),
                    "attention_count": attention_count,
                    "trigger_source": trigger_source,
                },
                request=request,
            )
            return result
        except Exception as exc:
            logger.exception("Task reminder execution %s failed", execution["id"])
            self.repository.fail_execution(
                execution["id"], type(exc).__name__.upper(), str(exc)
            )
            audit_event(
                "send_task_reminder", "task_reminder_execution",
                str(execution["id"]), requested_by,
                {
                    "subscription_id": subscription_id,
                    "error_type": type(exc).__name__,
                    "trigger_source": trigger_source,
                },
                request=request,
                result="FAILED",
            )
            raise TaskReminderExecutionError(
                "Task reminder execution failed"
            ) from exc

    @staticmethod
    def _validate_configuration(values: dict) -> None:
        groups = get_organization_service().list_groups(values["division"])
        assignee_group = values.get("assignee_group")
        if not groups or (
            assignee_group
            and not any(row["assignee_group"] == assignee_group for row in groups)
        ):
            raise TaskReminderValidationError(
                "Division or assignee group is not active/configured"
            )
        try:
            validate_recipient_domains(
                values["recipients"] + values["cc_recipients"]
            )
        except RecipientPolicyError as exc:
            raise TaskReminderValidationError(str(exc)) from exc
