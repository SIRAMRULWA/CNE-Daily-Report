"""
api/app.py
===========
FastAPI application factory.

Builds the app instance, registers routers, and configures CORS.
Imported by api/main.py (the stable Uvicorn entrypoint).
"""

import asyncio
import logging
import os
from contextlib import suppress

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from starlette.exceptions import HTTPException as StarletteHTTPException

from app_core.settings import get_settings
from api.auth import ensure_super_admin_user
from capabilities.organization import get_organization_service
from api.errors import (
    database_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from api.observability import RequestLoggingMiddleware
from api.v1.router import router as v1_router
from notifications.sender import run_due as run_due_reports
from notifications.task_reminder_sender import run_due as run_due_reminders

logger = logging.getLogger(__name__)


async def _report_email_scheduler(interval_seconds: int) -> None:
    """Check due email subscriptions without blocking the API event loop."""
    while True:
        try:
            await asyncio.to_thread(run_due_reports)
        except Exception:
            logger.exception("Automatic report email scheduler check failed")
        await asyncio.sleep(interval_seconds)


async def _task_reminder_scheduler(interval_seconds: int) -> None:
    """Run Admin-configured reminder schedules without blocking the API loop."""
    while True:
        try:
            await asyncio.to_thread(run_due_reminders)
        except Exception:
            logger.exception("Automatic task reminder scheduler check failed")
        await asyncio.sleep(interval_seconds)


def _cors_origins() -> list[str]:
    configured = os.getenv("API_CORS_ORIGINS", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]

    environment = os.getenv("ENVIRONMENT", "dev").lower()
    if environment in {"prod", "production", "qa"}:
        logger.warning("API_CORS_ORIGINS is not set; browser CORS requests will be blocked.")
        return []

    return ["*"]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ITIL Group Reports API",
        description=(
            "Serves the ITSS daily operations report data to Power BI "
            "and dashboard clients. Built on top of the ITIL Group Reports "
            "Automation pipeline."
        ),
        version="1.0.0",
        openapi_url="/api/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        contact={"name": "ITIL Group Reports API Support"},
        license_info={"name": "Internal use only"},
        openapi_tags=[
            {"name": "Authentication", "description": "Session creation and revocation."},
            {"name": "Users", "description": "Current-user and user administration resources."},
            {"name": "Security", "description": "Login and session security administration."},
            {"name": "Divisions", "description": "Division and assignee-group configuration."},
            {"name": "Daily Reports", "description": "Immutable selected-date report snapshots."},
            {"name": "Operations", "description": "Current operational records and summaries."},
            {"name": "Audit", "description": "Security and operator audit events."},
            {"name": "Report Subscriptions", "description": "Scheduled report delivery configuration."},
            {"name": "Report Deliveries", "description": "Report delivery history and manual delivery creation."},
            {"name": "Task Reminders", "description": "Real-time Helix reminder configuration and execution history."},
            {"name": "Automation", "description": "Machine-to-machine automation platform triggers."},
            {"name": "Helix Reports", "description": "Direct, read-only Helix report generation."},
            {"name": "Pipeline", "description": "Pipeline execution history."},
            {"name": "Maintenance", "description": "Restricted non-production maintenance jobs."},
            {"name": "Service", "description": "Service health and dependency status."},
        ],
    )

    default_openapi = app.openapi

    def versioned_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = default_openapi()
        schema["info"]["x-api-standards"] = "/docs/api-standards.md"
        app.openapi_schema = schema
        return schema

    app.openapi = versioned_openapi

    # Configure allowed browser origins with API_CORS_ORIGINS in QA/production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    @app.middleware("http")
    async def api_version_headers(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/api/v1/"):
            response.headers["API-Version"] = "1"
        return response

    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(psycopg2.Error, database_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.on_event("startup")
    def bootstrap_auth() -> None:
        try:
            ensure_super_admin_user(
                ensure_schema=settings.runtime.runtime_schema_bootstrap_enabled
            )
            if settings.runtime.runtime_schema_bootstrap_enabled:
                get_organization_service().ensure_storage()
            logger.info("Auth bootstrap complete")
        except Exception as exc:
            strict_startup = os.getenv("REQUIRE_DB_ON_STARTUP", "").lower() in {"1", "true", "yes"}
            production = os.getenv("ENVIRONMENT", "dev").lower() in {"prod", "production"}
            if strict_startup or production:
                raise
            logger.warning(
                "Auth bootstrap skipped because the database is unavailable: %s. "
                "Protected endpoints will fail until the database connection is restored.",
                exc,
            )

    @app.on_event("startup")
    async def start_report_email_scheduler() -> None:
        if not settings.schedulers.report_email_enabled:
            logger.info("Automatic report email scheduler is disabled")
            return
        interval_seconds = settings.schedulers.report_email_interval_seconds
        app.state.report_email_scheduler = asyncio.create_task(
            _report_email_scheduler(interval_seconds),
            name="report-email-scheduler",
        )
        logger.info("Automatic report email scheduler started; interval=%ss", interval_seconds)

    @app.on_event("startup")
    async def start_task_reminder_scheduler() -> None:
        if not settings.schedulers.task_reminder_enabled:
            logger.info("Automatic task reminder scheduler is disabled")
            return
        interval_seconds = settings.schedulers.task_reminder_interval_seconds
        app.state.task_reminder_scheduler = asyncio.create_task(
            _task_reminder_scheduler(interval_seconds), name="task-reminder-scheduler"
        )
        logger.info("Automatic task reminder scheduler started; interval=%ss", interval_seconds)

    @app.on_event("shutdown")
    async def stop_report_email_scheduler() -> None:
        task = getattr(app.state, "report_email_scheduler", None)
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        logger.info("Automatic report email scheduler stopped")

    @app.on_event("shutdown")
    async def stop_task_reminder_scheduler() -> None:
        task = getattr(app.state, "task_reminder_scheduler", None)
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        logger.info("Automatic task reminder scheduler stopped")

    # The versioned router is the only public application API.
    app.include_router(v1_router, prefix="/api")

    return app
