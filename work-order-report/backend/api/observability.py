"""Production logging configuration and HTTP request correlation."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def request_id_for(request: Request) -> str:
    """Return the request's stable correlation ID, creating it once if needed."""
    existing = getattr(request.state, "request_id", None)
    if existing:
        return existing
    supplied = request.headers.get("x-request-id", "").strip()
    request.state.request_id = supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else str(uuid4())
    return request.state.request_id


class JsonFormatter(logging.Formatter):
    """One-line JSON logs suitable for Docker and central log collectors."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in (
            "request_id", "method", "path", "status_code", "duration_ms",
            "actor", "role", "session_id", "client_ip", "event", "result",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Configure application logs once, before the FastAPI app is imported."""
    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = os.getenv("LOG_FORMAT", "json").strip().lower()
    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)sZ [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        ))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one completion log for every request with actor and correlation data."""

    async def dispatch(self, request: Request, call_next):
        request_id = request_id_for(request)
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        user = getattr(request.state, "current_user", None)
        actor = getattr(user, "email", None) or "anonymous"
        role = getattr(getattr(user, "role", None), "value", None)
        session_id = getattr(user, "session_id", None)
        response.headers["X-Request-ID"] = request_id
        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logging.getLogger("api.access").log(
            level,
            "HTTP request completed",
            extra={
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "actor": actor,
                "role": role,
                "session_id": str(session_id) if session_id is not None else None,
                "client_ip": _client_ip(request),
                "result": "SUCCESS" if response.status_code < 400 else "FAILED",
            },
        )
        return response
