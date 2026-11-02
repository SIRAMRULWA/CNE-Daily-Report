"""Shared API schemas used across versions and domains."""

from typing import Any

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    """Stable error contract returned by every API endpoint."""

    message: str
    detail: str
    error_code: str
    request_id: str
    details: Any | None = None


class PaginationMetadata(BaseModel):
    """Standard offset pagination metadata for future collection endpoints."""

    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    returned: int = Field(ge=0)
    total: int | None = Field(default=None, ge=0)


STANDARD_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Malformed request"},
    401: {"model": ErrorResponse, "description": "Authentication required or invalid"},
    403: {"model": ErrorResponse, "description": "Authenticated but not authorized"},
    404: {"model": ErrorResponse, "description": "Resource not found"},
    409: {"model": ErrorResponse, "description": "Resource state conflict"},
    422: {"model": ErrorResponse, "description": "Request validation failed"},
    500: {"model": ErrorResponse, "description": "Unexpected server error"},
    502: {"model": ErrorResponse, "description": "Upstream provider failure"},
    503: {"model": ErrorResponse, "description": "Required dependency unavailable"},
}
