"""HTTP adapter for Daily Report subscriptions and deliveries."""

from datetime import date, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from app_core.recipients import EMAIL_RE
from api.auth import AuthenticatedUser, Role, require_at_least
from capabilities.report_delivery import get_report_delivery_service
from capabilities.report_delivery.errors import (
    ReportDeliveryConflictError,
    ReportDeliveryNotFoundError,
    ReportDeliveryProviderError,
    ReportDeliveryValidationError,
)

class SubscriptionPayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    division: str = Field(min_length=1, max_length=100)
    assignee_group: str | None = None
    recipients: list[str] = Field(min_length=1)
    cc_recipients: list[str] = Field(default_factory=list)
    frequency: Literal["DAILY", "WEEKLY"] = "DAILY"
    weekday: int | None = Field(default=None, ge=0, le=6)
    send_time: time = time(8, 0)
    timezone: str = "Africa/Johannesburg"
    attachment_format: Literal["XLSX", "CSV"] = "XLSX"
    enabled: bool = False

    @field_validator("name", "division", "assignee_group")
    @classmethod
    def clean_text(cls, value):
        return value.strip() if value else value

    @field_validator("recipients", "cc_recipients")
    @classmethod
    def validate_emails(cls, values: list[str]) -> list[str]:
        cleaned = list(
            dict.fromkeys(
                value.strip().lower()
                for value in values
                if value and value.strip()
            )
        )
        if any(not EMAIL_RE.match(value) for value in cleaned):
            raise ValueError("Every recipient must be a valid email address")
        return cleaned

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def weekly_requires_day(self):
        if self.frequency == "WEEKLY" and self.weekday is None:
            raise ValueError(
                "weekday is required for WEEKLY subscriptions (Monday=0)"
            )
        if self.frequency == "DAILY":
            self.weekday = None
        return self


class AutomationSwitch(BaseModel):
    enabled: bool


class ManualSendPayload(BaseModel):
    division: str = Field(min_length=1, max_length=100)
    assignee_group: str | None = None
    recipients: list[str] = Field(min_length=1)
    cc_recipients: list[str] = Field(default_factory=list)
    report_date: date | None = None
    attachment_format: Literal["XLSX", "CSV"] = "XLSX"
    subject: str | None = Field(default=None, max_length=250)

    @field_validator("division", "assignee_group", "subject")
    @classmethod
    def clean_manual_text(cls, value):
        return value.strip() if value else value

    @field_validator("recipients", "cc_recipients")
    @classmethod
    def validate_manual_emails(cls, values: list[str]) -> list[str]:
        return SubscriptionPayload.validate_emails(values)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ReportDeliveryValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ReportDeliveryConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ReportDeliveryNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ReportDeliveryProviderError):
        return HTTPException(status_code=502, detail=str(exc))
    raise exc


# Compatibility helpers used by the task-reminder HTTP adapter. They delegate
# to the shared application policy while retaining existing HTTP behavior.
def _validate_scope(division: str, assignee_group: str | None) -> None:
    try:
        get_report_delivery_service().validate_scope(division, assignee_group)
    except ReportDeliveryValidationError as exc:
        raise _http_error(exc) from exc


def _validate_recipient_policy(addresses: list[str]) -> None:
    try:
        get_report_delivery_service().validate_recipient_policy(addresses)
    except ReportDeliveryValidationError as exc:
        raise _http_error(exc) from exc


def list_subscriptions():
    rows = get_report_delivery_service().list_subscriptions()
    return {"subscriptions": rows, "count": len(rows)}


def create_subscription(
    payload: SubscriptionPayload,
    request: Request,
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    try:
        return get_report_delivery_service().create_subscription(
            payload.model_dump(), user.email, request
        )
    except (
        ReportDeliveryValidationError,
        ReportDeliveryConflictError,
    ) as exc:
        raise _http_error(exc) from exc


def update_subscription(
    subscription_id: int,
    payload: SubscriptionPayload,
    request: Request,
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    try:
        return get_report_delivery_service().replace_subscription(
            subscription_id, payload.model_dump(), user.email, request
        )
    except (
        ReportDeliveryValidationError,
        ReportDeliveryConflictError,
        ReportDeliveryNotFoundError,
    ) as exc:
        raise _http_error(exc) from exc


def set_subscription_enabled(
    subscription_id: int,
    payload: AutomationSwitch,
    request: Request,
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    try:
        return get_report_delivery_service().set_subscription_enabled(
            subscription_id, payload.enabled, user.email, request
        )
    except (
        ReportDeliveryConflictError,
        ReportDeliveryNotFoundError,
    ) as exc:
        raise _http_error(exc) from exc


def send_manual_report(
    payload: ManualSendPayload,
    request: Request,
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    try:
        return get_report_delivery_service().send_manual(
            payload.model_dump(), user.email, request
        )
    except (
        ReportDeliveryValidationError,
        ReportDeliveryConflictError,
        ReportDeliveryNotFoundError,
        ReportDeliveryProviderError,
    ) as exc:
        raise _http_error(exc) from exc


def delete_subscription(
    subscription_id: int,
    request: Request,
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    try:
        return get_report_delivery_service().delete_subscription(
            subscription_id, user.email, request
        )
    except ReportDeliveryNotFoundError as exc:
        raise _http_error(exc) from exc


def list_deliveries(limit: int = Query(default=100, ge=1, le=1000)):
    rows = get_report_delivery_service().list_deliveries(limit)
    return {"deliveries": rows, "count": len(rows)}
