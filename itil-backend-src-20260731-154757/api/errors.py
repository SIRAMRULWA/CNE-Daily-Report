"""
api/errors.py
=============
User-facing API error responses.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

from api.observability import request_id_for


GENERIC_ERROR_MESSAGE = "Something went wrong while processing your request. Please try again or contact support."
HTTP_422_UNPROCESSABLE_CONTENT = 422

STATUS_MESSAGES = {
    status.HTTP_400_BAD_REQUEST: "The request could not be completed. Please check the information and try again.",
    status.HTTP_401_UNAUTHORIZED: "Please sign in again to continue.",
    status.HTTP_403_FORBIDDEN: "You do not have permission to perform this action.",
    status.HTTP_404_NOT_FOUND: "We could not find the requested information.",
    status.HTTP_409_CONFLICT: "This item already exists or conflicts with existing information.",
    HTTP_422_UNPROCESSABLE_CONTENT: "Some information is missing or invalid. Please check the form and try again.",
    status.HTTP_500_INTERNAL_SERVER_ERROR: GENERIC_ERROR_MESSAGE,
    status.HTTP_503_SERVICE_UNAVAILABLE: "The service is temporarily unavailable. Please try again shortly.",
}

ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_REQUIRED",
    status.HTTP_403_FORBIDDEN: "ACCESS_DENIED",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    HTTP_422_UNPROCESSABLE_CONTENT: "VALIDATION_ERROR",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}

DETAIL_MESSAGES = {
    "Authentication required": "Please sign in to continue.",
    "Invalid or expired access token": "Your session has expired. Please sign in again.",
    "Session not found": "Your session could not be found. Please sign in again.",
    "Session has been revoked": "Your session has ended. Please sign in again.",
    "Session has expired": "Your session has expired. Please sign in again.",
    "Account is not active": "Your account is not active. Please contact the system administrator.",
    "Password change required": "You need to change your temporary password before continuing.",
    "Insufficient role": "You do not have permission to perform this action.",
    "You cannot delete your own account": "You cannot delete your own account while you are signed in.",
    "The configured Super Admin cannot be deleted": "The main Super Admin account cannot be deleted.",
    "The configured Super Admin cannot be managed by another user": "The main Super Admin account cannot be managed by another user.",
    "The configured Super Admin role cannot be reassigned": "The main Super Admin role cannot be reassigned.",
    "User already exists": "This user already exists.",
    "User not found": "We could not find that user.",
    "Active session not found": "We could not find an active session to revoke.",
    "Division group mapping not found": "We could not find that division group mapping.",
}

DETAIL_ERROR_CODES = {
    "Authentication required": "AUTHENTICATION_REQUIRED",
    "Invalid or expired access token": "SESSION_EXPIRED",
    "Session not found": "SESSION_NOT_FOUND",
    "Session has been revoked": "SESSION_REVOKED",
    "Session has expired": "SESSION_EXPIRED",
    "Account is not active": "ACCOUNT_INACTIVE",
    "Password change required": "PASSWORD_CHANGE_REQUIRED",
    "Insufficient role": "ACCESS_DENIED",
    "You cannot delete your own account": "ACCESS_DENIED",
    "The configured Super Admin cannot be deleted": "ACCESS_DENIED",
    "The configured Super Admin cannot be managed by another user": "ACCESS_DENIED",
    "The configured Super Admin role cannot be reassigned": "ACCESS_DENIED",
    "Invalid email or password": "INVALID_CREDENTIALS",
    "Current password is incorrect": "CURRENT_PASSWORD_INCORRECT",
    "User already exists": "USER_ALREADY_EXISTS",
    "User not found": "USER_NOT_FOUND",
    "Active session not found": "SESSION_NOT_FOUND",
    "Division group mapping not found": "DIVISION_GROUP_NOT_FOUND",
}


def _request_id(request: Request) -> str:
    return request_id_for(request)


def _detail_to_message(detail: Any, status_code: int) -> str:
    if isinstance(detail, str) and detail in DETAIL_MESSAGES:
        return DETAIL_MESSAGES[detail]
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return STATUS_MESSAGES.get(status_code, GENERIC_ERROR_MESSAGE)


def _detail_to_error_code(detail: Any, status_code: int) -> str:
    if isinstance(detail, str) and detail in DETAIL_ERROR_CODES:
        return DETAIL_ERROR_CODES[detail]
    return ERROR_CODES.get(status_code, "API_ERROR")


def _error_response(
    request: Request,
    *,
    status_code: int,
    message: str,
    error_code: str | None = None,
    details: Any | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    content: dict[str, Any] = {
        "message": message,
        "detail": message,
        "error_code": error_code or ERROR_CODES.get(status_code, "API_ERROR"),
        "request_id": request_id,
    }
    if details is not None:
        content["details"] = details
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers={"X-Request-ID": request_id},
    )


def _validation_details(exc: RequestValidationError) -> list[dict[str, str]]:
    friendly_errors: list[dict[str, str]] = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", []) if part not in {"body", "query", "path"}]
        field = ".".join(location) if location else "request"
        friendly_errors.append(
            {
                "field": field,
                "message": str(error.get("msg", "Invalid value")),
            }
        )
    return friendly_errors


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = _detail_to_message(exc.detail, exc.status_code)
    response = _error_response(
        request,
        status_code=exc.status_code,
        message=message,
        error_code=_detail_to_error_code(exc.detail, exc.status_code),
    )
    if exc.status_code >= 500:
        logger.error(
            "API HTTP error request_id=%s status=%s path=%s detail=%r",
            response.headers["X-Request-ID"],
            exc.status_code,
            request.url.path,
            exc.detail,
        )
    return response


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    response = _error_response(
        request,
        status_code=HTTP_422_UNPROCESSABLE_CONTENT,
        message=STATUS_MESSAGES[HTTP_422_UNPROCESSABLE_CONTENT],
        details=_validation_details(exc),
    )
    logger.info(
        "API validation error request_id=%s path=%s errors=%s",
        response.headers["X-Request-ID"],
        request.url.path,
        _validation_details(exc),
    )
    return response


async def database_error_handler(request: Request, exc: psycopg2.Error) -> JSONResponse:
    unavailable = isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError))
    response = _error_response(
        request,
        status_code=(status.HTTP_503_SERVICE_UNAVAILABLE if unavailable else status.HTTP_500_INTERNAL_SERVER_ERROR),
        message=(
            "We cannot reach the reporting database right now. Please try again shortly."
            if unavailable
            else "The reporting database could not complete this request. Please contact support."
        ),
        error_code="DATABASE_UNAVAILABLE" if unavailable else "DATABASE_QUERY_FAILED",
    )
    logger.error(
        "Database operation failed request_id=%s path=%s",
        response.headers["X-Request-ID"],
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return response


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    response = _error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=GENERIC_ERROR_MESSAGE,
        error_code="INTERNAL_ERROR",
    )
    logger.error(
        "Unhandled API error request_id=%s path=%s",
        response.headers["X-Request-ID"],
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return response
