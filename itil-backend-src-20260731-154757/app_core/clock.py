"""Canonical UTC and workspace-local clocks."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app_core.settings import get_settings


def workspace_zone() -> ZoneInfo:
    return ZoneInfo(get_settings().runtime.workspace_timezone)


def utc_now() -> datetime:
    return datetime.now(UTC)


def workspace_now() -> datetime:
    return utc_now().astimezone(workspace_zone())


def workspace_now_naive() -> datetime:
    """Return the legacy pipeline representation: workspace-local, timezone-naive."""
    return workspace_now().replace(tzinfo=None)


def to_workspace(value: datetime) -> datetime:
    """Convert an aware instant to the workspace timezone.

    Naive values are interpreted as already being workspace-local, preserving
    the existing pipeline contract.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=workspace_zone())
    return value.astimezone(workspace_zone())


def to_workspace_naive(value: datetime) -> datetime:
    return to_workspace(value).replace(tzinfo=None)

