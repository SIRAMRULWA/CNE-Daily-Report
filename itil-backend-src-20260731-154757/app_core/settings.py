"""Typed, centrally validated application settings.

Existing environment variable names remain the public deployment contract.
Feature modules can migrate to these settings incrementally.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def env_flag(name: str, default: bool = False) -> bool:
    """Read a backward-compatible boolean environment flag."""
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in TRUE_VALUES


def _positive_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class RuntimeSettings:
    environment: str
    workspace_timezone: str
    log_level: str
    log_format: str
    require_db_on_startup: bool
    runtime_schema_bootstrap_enabled: bool

    @property
    def production(self) -> bool:
        return self.environment in {"prod", "production"}


@dataclass(frozen=True)
class DatabaseSettings:
    url: str | None
    host: str
    port: int
    name: str
    user: str
    password: str
    connect_timeout: int
    connect_retries: int
    retry_delay_seconds: float


@dataclass(frozen=True)
class SchedulerSettings:
    report_email_enabled: bool
    report_email_interval_seconds: int
    task_reminder_enabled: bool
    task_reminder_interval_seconds: int


@dataclass(frozen=True)
class AppSettings:
    runtime: RuntimeSettings
    database: DatabaseSettings
    schedulers: SchedulerSettings

    @classmethod
    def from_env(cls) -> "AppSettings":
        timezone_name = os.getenv("WORKSPACE_TIMEZONE", "Africa/Johannesburg").strip()
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"WORKSPACE_TIMEZONE is invalid: {timezone_name}") from exc

        return cls(
            runtime=RuntimeSettings(
                environment=os.getenv("ENVIRONMENT", "dev").strip().lower(),
                workspace_timezone=timezone_name,
                log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
                log_format=os.getenv("LOG_FORMAT", "json").strip().lower(),
                require_db_on_startup=env_flag("REQUIRE_DB_ON_STARTUP", False),
                runtime_schema_bootstrap_enabled=env_flag(
                    "RUNTIME_SCHEMA_BOOTSTRAP_ENABLED", False
                ),
            ),
            database=DatabaseSettings(
                url=os.getenv("DATABASE_URL") or None,
                host=os.getenv("DB_HOST", "localhost"),
                port=_positive_int("DB_PORT", 5432),
                name=os.getenv("DB_NAME", "itil_reports"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", ""),
                connect_timeout=_positive_int("DB_CONNECT_TIMEOUT", 5),
                connect_retries=_positive_int("DB_CONNECT_RETRIES", 3),
                retry_delay_seconds=max(float(os.getenv("DB_RETRY_DELAY_SECONDS", "2")), 0),
            ),
            schedulers=SchedulerSettings(
                report_email_enabled=env_flag("REPORT_EMAIL_SCHEDULER_ENABLED", True),
                report_email_interval_seconds=_positive_int(
                    "REPORT_EMAIL_SCHEDULER_INTERVAL_SECONDS", 60, minimum=30
                ),
                task_reminder_enabled=env_flag("TASK_REMINDER_SCHEDULER_ENABLED", True),
                task_reminder_interval_seconds=_positive_int(
                    "TASK_REMINDER_SCHEDULER_INTERVAL_SECONDS", 60, minimum=30
                ),
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return the process-wide immutable settings snapshot."""
    return AppSettings.from_env()


def reset_settings_cache() -> None:
    """Clear cached settings for tests and controlled process reconfiguration."""
    get_settings.cache_clear()
