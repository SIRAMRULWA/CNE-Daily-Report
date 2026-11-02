"""Canonical, versioned, resource-oriented API routes."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, model_validator

from api.auth import AuthenticatedUser, Role, require_at_least, require_roles
from api.routers import auth, daily_report, divisions, health, helix_raw_reports
from api.routers import report_emails, testing_cleanup, workspace
from api.routers import task_reminders
from api.schemas import STANDARD_ERROR_RESPONSES


router = APIRouter(prefix="/v1", responses=STANDARD_ERROR_RESPONSES)
read_access = [Depends(require_at_least(Role.READ_ONLY))]
admin_access = [Depends(require_at_least(Role.ADMIN))]
super_admin_access = [Depends(require_roles(Role.SUPER_ADMIN))]


class UserPatch(BaseModel):
    """Fields an administrator may change on an existing user."""

    status: auth.AccountStatus | None = None
    role: Role | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.status is None and self.role is None:
            raise ValueError("Supply at least one of: status, role")
        if self.role == Role.SUPER_ADMIN:
            raise ValueError("SUPER_ADMIN is reserved for the configured system owner")
        return self


def update_user(
    payload: UserPatch,
    request: Request,
    user_id: int = Path(..., ge=1),
    current_user: AuthenticatedUser = Depends(require_roles(Role.SUPER_ADMIN)),
):
    """Apply one partial update to a user resource."""
    result = None
    if payload.status is not None:
        result = auth.update_user_status(
            auth.StatusUpdateRequest(status=payload.status), request, user_id, current_user
        )
    if payload.role is not None:
        result = auth.update_user_role(
            auth.RoleUpdateRequest(role=payload.role), request, user_id, current_user
        )
    return result


def update_subscription(
    payload: report_emails.AutomationSwitch,
    request: Request,
    subscription_id: int = Path(..., ge=1),
    user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    """Partially update a report subscription's automation state."""
    return report_emails.set_subscription_enabled(subscription_id, payload, request, user)


def get_daily_report(
    report_date: date | None = Query(default=None),
    period: Literal["day", "week"] = Query(default="day"),
    division: str | None = Query(default=None),
    assignee_group: str | None = Query(default=None),
    include_dates: bool = Query(default=True),
    date_limit: int = Query(default=90, ge=1, le=366),
    include_records: bool = Query(default=False),
    sla: str | None = Query(default=None),
    category: str | None = Query(default=None),
):
    """Return one selected-date report contract with supported query parameters."""
    return daily_report.daily_report_view(
        report_date=report_date,
        period=period,
        division=division,
        assignee_group=assignee_group,
        include_dates=include_dates,
        date_limit=date_limit,
        include_records=include_records,
        sla=sla,
        category=category,
    )


def list_daily_report_records(
    report_date: date | None = Query(default=None),
    period: Literal["day", "week"] = Query(default="day"),
    division: str | None = Query(default=None),
    assignee_group: str | None = Query(default=None),
    sla: str | None = Query(default=None),
    category: str | None = Query(default=None),
):
    """Return records from the selected historical report snapshot."""
    return daily_report.daily_report_records(
        report_date=report_date,
        period=period,
        division=division,
        assignee_group=assignee_group,
        sla=sla,
        category=category,
    )


def add(
    path: str,
    endpoint,
    methods: list[str],
    *,
    tags: list[str],
    summary: str,
    dependencies: list | None = None,
    status_code: int | None = None,
    response_model=dict,
) -> None:
    router.add_api_route(
        path,
        endpoint,
        methods=methods,
        tags=tags,
        summary=summary,
        dependencies=dependencies,
        status_code=status_code,
        response_model=response_model,
    )


# Authentication and the current principal.
add("/auth/sessions", auth.login, ["POST"], tags=["Authentication"], summary="Create an authenticated session", status_code=201, response_model=auth.TokenResponse)
add("/auth/sessions/current", auth.logout, ["DELETE"], tags=["Authentication"], summary="Revoke the current session")
add("/users/current", auth.me, ["GET"], tags=["Users"], summary="Get the current user")
add("/users/current/password", auth.change_password, ["PATCH"], tags=["Users"], summary="Change the current user's password")

# User and session administration.
add("/users", auth.list_users, ["GET"], tags=["Users"], summary="List users", dependencies=super_admin_access)
add("/users", auth.create_user, ["POST"], tags=["Users"], summary="Create a user", status_code=201)
add("/users/{user_id}", update_user, ["PATCH"], tags=["Users"], summary="Update a user")
add("/users/{user_id}", auth.delete_user, ["DELETE"], tags=["Users"], summary="Delete a user")
add("/users/{user_id}/password-reset", auth.reset_password, ["POST"], tags=["Users"], summary="Reset a user's password")
add("/login-attempts", auth.login_history, ["GET"], tags=["Security"], summary="List login attempts", dependencies=super_admin_access)
add("/sessions", auth.active_sessions, ["GET"], tags=["Security"], summary="List active sessions", dependencies=super_admin_access)
add("/sessions/{session_id}", auth.revoke_session, ["DELETE"], tags=["Security"], summary="Revoke a session")

# Configuration resources.
add("/divisions", divisions.get_divisions, ["GET"], tags=["Divisions"], summary="List divisions", dependencies=read_access)
add("/divisions", divisions.create_division, ["POST"], tags=["Divisions"], summary="Create a division", status_code=201)
add("/divisions/{division}/groups", divisions.get_division_groups, ["GET"], tags=["Divisions"], summary="List division groups", dependencies=read_access)
add("/divisions/{division}/groups", divisions.create_division_groups, ["POST"], tags=["Divisions"], summary="Add division groups", status_code=201)
add("/divisions/{division}/groups/{assignee_group}", divisions.delete_division_group, ["DELETE"], tags=["Divisions"], summary="Remove a division group")
add("/division-group-seed-jobs", divisions.seed_default_groups, ["POST"], tags=["Divisions"], summary="Seed default division groups")

# Snapshot reporting and live operational data are intentionally separate.
add("/daily-reports", get_daily_report, ["GET"], tags=["Daily Reports"], summary="Get a daily report snapshot", dependencies=read_access)
add("/daily-reports/records", list_daily_report_records, ["GET"], tags=["Daily Reports"], summary="List records from a report snapshot", dependencies=read_access)
add("/operational-records", workspace.workspace_records, ["GET"], tags=["Operations"], summary="List current operational records", dependencies=read_access)
add("/operational-records/summary", workspace.workspace_summary, ["GET"], tags=["Operations"], summary="Summarize current operational records", dependencies=read_access)
add("/audit-events", workspace.workspace_activity_log, ["GET"], tags=["Audit"], summary="List audit events", dependencies=super_admin_access)

# Report subscription and delivery resources.
add("/report-subscriptions", report_emails.list_subscriptions, ["GET"], tags=["Report Subscriptions"], summary="List report subscriptions", dependencies=admin_access)
add("/report-subscriptions", report_emails.create_subscription, ["POST"], tags=["Report Subscriptions"], summary="Create a report subscription", status_code=201)
add("/report-subscriptions/{subscription_id}", report_emails.update_subscription, ["PUT"], tags=["Report Subscriptions"], summary="Replace a report subscription")
add("/report-subscriptions/{subscription_id}", update_subscription, ["PATCH"], tags=["Report Subscriptions"], summary="Update a report subscription")
add("/report-subscriptions/{subscription_id}", report_emails.delete_subscription, ["DELETE"], tags=["Report Subscriptions"], summary="Delete a report subscription")
add("/report-deliveries", report_emails.list_deliveries, ["GET"], tags=["Report Deliveries"], summary="List report deliveries", dependencies=admin_access)
add("/report-deliveries", report_emails.send_manual_report, ["POST"], tags=["Report Deliveries"], summary="Create a manual report delivery", status_code=201)

# Real-time outstanding-task reminder configuration and execution.
add("/task-reminder-subscriptions", task_reminders.list_subscriptions, ["GET"], tags=["Task Reminders"], summary="List task reminder subscriptions", dependencies=admin_access)
add("/task-reminder-subscriptions", task_reminders.create_subscription, ["POST"], tags=["Task Reminders"], summary="Create a task reminder subscription", status_code=201, dependencies=admin_access)
add("/task-reminder-subscriptions/{subscription_id}", task_reminders.replace_subscription, ["PUT"], tags=["Task Reminders"], summary="Replace a task reminder subscription", dependencies=admin_access)
add("/task-reminder-subscriptions/{subscription_id}", task_reminders.update_subscription, ["PATCH"], tags=["Task Reminders"], summary="Update a task reminder subscription", dependencies=admin_access)
add("/task-reminder-subscriptions/{subscription_id}", task_reminders.delete_subscription, ["DELETE"], tags=["Task Reminders"], summary="Delete a task reminder subscription", dependencies=admin_access)
add("/task-reminder-executions", task_reminders.list_executions, ["GET"], tags=["Task Reminders"], summary="List task reminder executions", dependencies=admin_access)
add("/task-reminder-executions", task_reminders.execute_manual, ["POST"], tags=["Task Reminders"], summary="Execute a task reminder manually", status_code=201, dependencies=admin_access)
add("/automation/task-reminder-executions", task_reminders.execute_automation, ["POST"], tags=["Automation"], summary="Execute a scheduled task reminder", status_code=201)

# Direct Helix reporting.
add("/helix-reports/fields", helix_raw_reports.raw_report_fields, ["GET"], tags=["Helix Reports"], summary="List Helix report fields", dependencies=read_access)
add("/helix-reports/filters", helix_raw_reports.raw_report_filters, ["GET"], tags=["Helix Reports"], summary="List Helix report filters", dependencies=read_access)
add("/helix-reports", helix_raw_reports.create_raw_report, ["POST"], tags=["Helix Reports"], summary="Generate a Helix report", dependencies=read_access)

# Service health, pipeline history, and guarded maintenance.
add("/health", health.health, ["GET"], tags=["Service"], summary="Get service health")
add("/pipeline-runs", health.run_log, ["GET"], tags=["Pipeline"], summary="List pipeline runs", dependencies=super_admin_access)
add("/maintenance/data-cleanup-jobs", testing_cleanup.cleanup_test_data, ["POST"], tags=["Maintenance"], summary="Preview or execute test-data cleanup")
