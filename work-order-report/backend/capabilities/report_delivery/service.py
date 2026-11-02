"""Application service for Daily Report subscriptions and deliveries."""

from __future__ import annotations

from typing import Protocol

from app_core.audit import audit_event
from app_core.recipients import RecipientPolicyError, validate_recipient_domains
from app_core.settings import env_flag
from capabilities.organization import get_organization_service
from capabilities.report_delivery.errors import (
    ReportDeliveryConflictError,
    ReportDeliveryNotFoundError,
    ReportDeliveryProviderError,
    ReportDeliveryValidationError,
)
from notifications.reports import attachment, html_body, report_data
from capabilities.daily_reports import email_closed_changes
from notifications.transport import configured_transport


class ReportDeliveryStore(Protocol):
    def list_subscriptions(self) -> list[dict]: ...
    def create_subscription(self, values: dict, actor: str) -> dict: ...
    def replace_subscription(
        self, subscription_id: int, values: dict, actor: str
    ) -> dict | None: ...
    def set_enabled(
        self, subscription_id: int, enabled: bool, actor: str
    ) -> dict | None: ...
    def soft_delete_subscription(self, subscription_id: int, actor: str) -> bool: ...
    def list_deliveries(self, limit: int) -> list[dict]: ...
    def latest_report_date(self, division: str, assignee_group: str | None): ...
    def start_manual_delivery(self, report_date, recipients, actor: str) -> int: ...
    def complete_manual_delivery(
        self, delivery_id: int, record_count: int, provider: str, message_id
    ) -> None: ...
    def fail_manual_delivery(self, delivery_id: int, error: str) -> None: ...


class ReportDeliveryService:
    def __init__(self, repository: ReportDeliveryStore):
        self.repository = repository

    def validate_scope(self, division: str, assignee_group: str | None) -> None:
        groups = get_organization_service().list_groups(division)
        if not groups or (
            assignee_group
            and not any(row["assignee_group"] == assignee_group for row in groups)
        ):
            raise ReportDeliveryValidationError(
                "Division or assignee group is not active/configured"
            )

    def validate_recipient_policy(self, addresses: list[str]) -> None:
        try:
            validate_recipient_domains(addresses)
        except RecipientPolicyError as exc:
            raise ReportDeliveryValidationError(str(exc)) from exc

    def list_subscriptions(self) -> list[dict]:
        return self.repository.list_subscriptions()

    def create_subscription(
        self, values: dict, actor: str, request=None
    ) -> dict:
        self._validate_subscription(values)
        row = self.repository.create_subscription(values, actor)
        self._audit_subscription(
            "create_report_email_subscription", row["id"], values, actor, request
        )
        return row

    def replace_subscription(
        self, subscription_id: int, values: dict, actor: str, request=None
    ) -> dict:
        self._validate_subscription(values)
        row = self.repository.replace_subscription(subscription_id, values, actor)
        if row is None:
            raise ReportDeliveryNotFoundError("Subscription not found")
        self._audit_subscription(
            "update_report_email_subscription",
            subscription_id, values, actor, request,
        )
        return row

    def set_subscription_enabled(
        self, subscription_id: int, enabled: bool, actor: str, request=None
    ) -> dict:
        self._validate_automation(enabled)
        row = self.repository.set_enabled(subscription_id, enabled, actor)
        if row is None:
            raise ReportDeliveryNotFoundError("Subscription not found")
        audit_event(
            "toggle_report_email_subscription", "report_email_subscription",
            str(subscription_id), actor, {"enabled": enabled}, request=request,
        )
        return row

    def delete_subscription(
        self, subscription_id: int, actor: str, request=None
    ) -> dict:
        if not self.repository.soft_delete_subscription(subscription_id, actor):
            raise ReportDeliveryNotFoundError("Subscription not found")
        audit_event(
            "delete_report_email_subscription", "report_email_subscription",
            str(subscription_id), actor, request=request,
        )
        return {"id": subscription_id, "deleted": True}

    def list_deliveries(self, limit: int) -> list[dict]:
        return self.repository.list_deliveries(limit)

    def send_manual(
        self, values: dict, actor: str, request=None
    ) -> dict:
        if not env_flag("REPORT_EMAIL_MANUAL_SEND_ENABLED"):
            raise ReportDeliveryConflictError(
                "Manual report email testing is disabled on this server"
            )
        self.validate_scope(values["division"], values.get("assignee_group"))
        self.validate_recipient_policy(
            values["recipients"] + values["cc_recipients"]
        )
        selected_date = values.get("report_date") or self.repository.latest_report_date(
            values["division"], values.get("assignee_group")
        )
        if selected_date is None:
            raise ReportDeliveryNotFoundError(
                "No Daily Report snapshot exists for the requested scope"
            )
        summary, records = report_data(
            selected_date, values["division"], values.get("assignee_group")
        )
        if not summary:
            raise ReportDeliveryNotFoundError(
                "No Daily Report snapshot exists for the requested date and scope"
            )

        delivery_id = self.repository.start_manual_delivery(
            selected_date, values["recipients"] + values["cc_recipients"], actor
        )
        try:
            transport = configured_transport()
            file = attachment(
                records, values["division"], selected_date,
                values["attachment_format"],
                email_closed_changes(
                    selected_date, values["division"], values.get("assignee_group")
                ),
            )
            scope = values.get("assignee_group") or values["division"]
            message_id = transport.send(
                values["recipients"], values["cc_recipients"],
                values.get("subject")
                or f"Daily Report - {scope} - {selected_date.isoformat()}",
                html_body(
                    "Manual Daily Report", selected_date, values["division"],
                    values.get("assignee_group"), summary, len(records),
                    values["attachment_format"],
                ),
                file,
            )
            self.repository.complete_manual_delivery(
                delivery_id, len(records), transport.provider, message_id
            )
        except Exception as exc:
            self.repository.fail_manual_delivery(delivery_id, str(exc))
            audit_event(
                "send_manual_report_email", "report_email_delivery",
                str(delivery_id), actor,
                {
                    "division": values["division"],
                    "assignee_group": values.get("assignee_group"),
                    "report_date": str(selected_date),
                    "recipient_count": len(values["recipients"]),
                    "error_type": type(exc).__name__,
                },
                request=request, result="FAILED",
            )
            raise ReportDeliveryProviderError(
                "Report email delivery failed"
            ) from exc

        audit_event(
            "send_manual_report_email", "report_email_delivery", str(delivery_id),
            actor,
            {
                "division": values["division"],
                "assignee_group": values.get("assignee_group"),
                "report_date": str(selected_date),
                "recipient_count": len(values["recipients"]),
                "cc_recipient_count": len(values["cc_recipients"]),
                "record_count": len(records),
                "provider": transport.provider,
            },
            request=request,
        )
        return {
            "delivery_id": delivery_id,
            "status": "SENT",
            "report_date": selected_date,
            "record_count": len(records),
            "provider": transport.provider,
        }

    def _validate_subscription(self, values: dict) -> None:
        self.validate_scope(values["division"], values.get("assignee_group"))
        self.validate_recipient_policy(
            values["recipients"] + values["cc_recipients"]
        )
        self._validate_automation(values["enabled"])

    @staticmethod
    def _validate_automation(enabled: bool) -> None:
        if enabled and not env_flag("REPORT_EMAIL_AUTOMATION_APPROVED"):
            raise ReportDeliveryConflictError(
                "Automatic report email delivery is not approved/enabled on this server"
            )

    @staticmethod
    def _audit_subscription(
        action: str, subscription_id: int, values: dict, actor: str, request
    ) -> None:
        audit_event(
            action, "report_email_subscription", str(subscription_id), actor,
            {
                "name": values["name"],
                "division": values["division"],
                "assignee_group": values.get("assignee_group"),
                "frequency": values["frequency"],
                "send_time": str(values["send_time"]),
                "enabled": values["enabled"],
                "recipient_count": len(values["recipients"]),
                "cc_recipient_count": len(values["cc_recipients"]),
            },
            request=request,
        )
