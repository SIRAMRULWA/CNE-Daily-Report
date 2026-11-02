"""Configuration, automation trigger, and history handlers for task reminders."""

import os
import secrets
from datetime import time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException, Path, Query, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator, model_validator

from app_core.recipients import EMAIL_RE
from api.auth import AuthenticatedUser, Role, require_at_least
from capabilities.task_reminders import get_task_reminder_service
from capabilities.task_reminders.errors import (
    TaskReminderConflictError,
    TaskReminderExecutionError,
    TaskReminderNotFoundError,
    TaskReminderValidationError,
)

automation_key_header = APIKeyHeader(name="X-Automation-Key", auto_error=False)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TaskReminderValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, TaskReminderConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, TaskReminderNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, TaskReminderExecutionError):
        return HTTPException(status_code=502, detail=str(exc))
    raise exc


class ReminderSubscriptionPayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    division: str = Field(min_length=1, max_length=100)
    assignee_group: str | None = Field(default=None, max_length=200)
    recipients: list[str] = Field(min_length=1)
    cc_recipients: list[str] = Field(default_factory=list)
    subject: str | None = Field(default=None, max_length=250)
    frequency: Literal["DAILY", "WEEKLY"] = "DAILY"
    weekday: int | None = Field(default=None, ge=0, le=6)
    send_time: time = time(10, 0)
    timezone: str = "Africa/Johannesburg"
    max_records: int = Field(default=10000, ge=1, le=50000)
    enabled: bool = False

    @field_validator("name", "division", "assignee_group", "subject")
    @classmethod
    def clean_text(cls, value):
        return value.strip() if value else value

    @field_validator("recipients", "cc_recipients")
    @classmethod
    def validate_emails(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip().lower() for value in values if value and value.strip()))
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
            raise ValueError("weekday is required for WEEKLY reminders (Monday=0)")
        if self.frequency == "DAILY":
            self.weekday = None
        return self


class ReminderSwitch(BaseModel):
    enabled: bool


class ReminderExecutionPayload(BaseModel):
    subscription_id: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)

    @field_validator("idempotency_key")
    @classmethod
    def clean_key(cls, value):
        return value.strip() if value else value


def require_automation_key(
    key: str | None = Depends(automation_key_header),
) -> str:
    configured = os.getenv("TASK_REMINDER_AUTOMATION_KEY", "")
    if not configured:
        raise HTTPException(status_code=503, detail="Task reminder automation is not configured")
    if not key or not secrets.compare_digest(key, configured):
        raise HTTPException(status_code=401, detail="Invalid automation credentials")
    return "automation-platform"


def list_subscriptions(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    rows = get_task_reminder_service().list_subscriptions(limit, offset)
    return {"subscriptions": rows, "count": len(rows), "limit": limit, "offset": offset}


def create_subscription(
    payload: ReminderSubscriptionPayload,
    request: Request,
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    try:
        return get_task_reminder_service().create_subscription(
            payload.model_dump(), user.email, request
        )
    except TaskReminderValidationError as exc:
        raise _http_error(exc) from exc


def replace_subscription(
    payload: ReminderSubscriptionPayload,
    request: Request,
    subscription_id: int = Path(..., ge=1),
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    try:
        return get_task_reminder_service().replace_subscription(
            subscription_id, payload.model_dump(), user.email, request
        )
    except (TaskReminderValidationError, TaskReminderNotFoundError) as exc:
        raise _http_error(exc) from exc


def update_subscription(
    payload: ReminderSwitch,
    request: Request,
    subscription_id: int = Path(..., ge=1),
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    try:
        return get_task_reminder_service().set_enabled(
            subscription_id, payload.enabled, user.email, request
        )
    except TaskReminderNotFoundError as exc:
        raise _http_error(exc) from exc


def delete_subscription(
    request: Request,
    subscription_id: int = Path(..., ge=1),
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    try:
        return get_task_reminder_service().delete_subscription(
            subscription_id, user.email, request
        )
    except TaskReminderNotFoundError as exc:
        raise _http_error(exc) from exc


def list_executions(
    subscription_id: int | None = Query(default=None, ge=1),
    execution_status: Literal["RUNNING", "SENT", "FAILED"] | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    rows = get_task_reminder_service().list_executions(
        subscription_id, execution_status, limit, offset
    )
    return {"executions": rows, "count": len(rows), "limit": limit, "offset": offset}


def _execute(payload: ReminderExecutionPayload, trigger_source: str, actor: str, request: Request):
    key = payload.idempotency_key or f"manual-{secrets.token_urlsafe(18)}"
    try:
        return get_task_reminder_service().execute(
            payload.subscription_id, key, trigger_source, actor, request=request
        )
    except (
        TaskReminderNotFoundError,
        TaskReminderConflictError,
        TaskReminderExecutionError,
    ) as exc:
        raise _http_error(exc) from exc


def execute_manual(
    payload: ReminderExecutionPayload,
    request: Request,
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    return _execute(payload, "MANUAL", user.email, request)


def execute_automation(
    payload: ReminderExecutionPayload,
    request: Request,
    actor: str = Depends(require_automation_key),
):
    if not payload.idempotency_key:
        raise HTTPException(status_code=422,
                            detail="idempotency_key is required for automation triggers")
    return _execute(payload, "AUTOMATION", actor, request)
