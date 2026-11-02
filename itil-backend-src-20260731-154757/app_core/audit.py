"""Delivery-neutral audit recording.

The optional request object is accessed by protocol rather than importing
FastAPI, allowing API, workers, CLI jobs, and schedulers to share this service.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def client_ip(request: Any) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if getattr(request, "client", None) else None


def parse_user_agent(user_agent: str | None) -> tuple[str | None, str | None]:
    value = user_agent or ""
    browser = None
    if "Edg/" in value:
        browser = "Edge"
    elif "Chrome/" in value:
        browser = "Chrome"
    elif "Firefox/" in value:
        browser = "Firefox"
    elif "Safari/" in value:
        browser = "Safari"

    os_name = None
    if "Windows" in value:
        os_name = "Windows"
    elif "Mac OS X" in value:
        os_name = "macOS"
    elif "Android" in value:
        os_name = "Android"
    elif "iPhone" in value or "iPad" in value:
        os_name = "iOS"
    elif "Linux" in value:
        os_name = "Linux"
    return browser, os_name


def audit_event(
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    actor: str | None = None,
    details: dict[str, Any] | None = None,
    request: Any | None = None,
    result: str = "SUCCESS",
) -> None:
    """Persist and log one audit event from any application entrypoint."""
    from pipeline.activity_log import record_activity

    user_agent = request.headers.get("user-agent") if request else None
    browser, os_name = parse_user_agent(user_agent)
    enriched = {
        **(details or {}),
        "result": result,
        "request_id": getattr(request.state, "request_id", None) if request else None,
        "http_method": request.method if request else None,
        "http_path": request.url.path if request else None,
        "ip_address": client_ip(request) if request else None,
        "user_agent": user_agent,
        "browser": browser,
        "operating_system": os_name,
    }
    record_activity(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        details=enriched,
    )
    logger.info(
        "Audit event action=%s entity_type=%s entity_id=%s actor=%s result=%s",
        action,
        entity_type,
        entity_id,
        actor or "system",
        result,
        extra={
            "event": "audit_event",
            "request_id": enriched.get("request_id"),
            "method": enriched.get("http_method"),
            "path": enriched.get("http_path"),
            "actor": actor or "system",
            "result": result,
        },
    )
