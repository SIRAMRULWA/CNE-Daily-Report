"""Standalone, read-only raw report endpoints backed directly by Helix."""

from datetime import datetime

import requests
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from api.auth import audit_event
from config.mappings import CLOSED_STATUSES
from helix.extractor import (
    HELIX_FIELD_MAP,
    HELIX_RAW_REPORT_DATE_FIELDS,
    HelixExtractor,
)
from pipeline.division_groups import list_division_groups
class RawReportRequest(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    date_field: str = "Create Date"
    fields: list[str] | None = None
    divisions: list[str] | None = None
    assignee_groups: list[str] | None = None
    assignees: list[str] | None = None
    statuses: list[str] | None = None
    include_closed: bool = Field(
        default=False,
        description=(
            "Include Closed, Cancelled, Success, and Bypassed tasks when "
            "statuses is also supplied. Omit statuses to return every status."
        ),
    )
    categories: list[str] | None = None
    request_ids: list[str] | None = None
    task_ids: list[str] | None = None
    calculate_sla: bool = Field(
        default=False,
        description=(
            "Add report_category, sla_status, and hours_open using the "
            "Daily Report SLA rules. This calculation is read-only."
        ),
    )
    limit: int = Field(default=5000, ge=1, le=100000)

    @field_validator("date_field")
    @classmethod
    def validate_date_field(cls, value: str) -> str:
        if value not in HELIX_RAW_REPORT_DATE_FIELDS:
            allowed = ", ".join(sorted(HELIX_RAW_REPORT_DATE_FIELDS))
            raise ValueError(f"date_field must be one of: {allowed}")
        return value

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("fields cannot be empty; omit it to return every mapped field")
        deduped = list(dict.fromkeys(value))
        unknown = sorted(set(deduped) - set(HELIX_FIELD_MAP.values()))
        if unknown:
            raise ValueError(f"Unsupported fields: {', '.join(unknown)}")
        return deduped

    @field_validator(
        "divisions",
        "assignee_groups",
        "assignees",
        "statuses",
        "categories",
        "request_ids",
        "task_ids",
    )
    @classmethod
    def clean_filters(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned = list(dict.fromkeys(item.strip() for item in value if item and item.strip()))
        if not cleaned:
            raise ValueError("Filter lists cannot be empty; omit them to query all groups")
        return cleaned

    @model_validator(mode="after")
    def validate_range(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must be supplied together")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("end must be on or after start")
        if self.start is None and not (self.request_ids or self.task_ids):
            raise ValueError("Supply a date range, request_ids, or task_ids")
        return self


def raw_report_fields():
    """Return the allow-listed fields and supported time-range columns."""
    return {
        "fields": [
            {"name": canonical, "helix_field": source}
            for source, canonical in HELIX_FIELD_MAP.items()
        ],
        "date_fields": sorted(HELIX_RAW_REPORT_DATE_FIELDS),
        "default_date_field": "Create Date",
        "common_statuses": ["Assigned", "Staged", "Work in Progress", "Pending"],
        "closed_statuses": sorted(CLOSED_STATUSES),
        "status_filter_help": (
            "Omit statuses to return every status, including closed tasks. "
            "When filtering open statuses, set include_closed=true to add all "
            "recognized closed statuses."
        ),
        "derived_categories": ["Faults", "Security", "Alarm", "Change", "Work Order", "PBI"],
        "derived_sla_fields": [
            "report_category",
            "sla_status",
            "hours_open",
            "sla_calculated_at",
        ],
    }


def raw_report_filters():
    """Return active divisions and their selectable assignee groups."""
    rows = list_division_groups()
    divisions: dict[str, list[str]] = {}
    for row in rows:
        divisions.setdefault(row["division"], []).append(row["assignee_group"])
    return {
        "divisions": [
            {"name": division, "assignee_groups": groups}
            for division, groups in sorted(divisions.items())
        ],
        "count": len(divisions),
    }


def _resolve_assignee_groups(payload: RawReportRequest) -> list[str]:
    """Resolve selected divisions and explicit groups into one Helix filter."""
    selected = list(payload.assignee_groups or [])
    if payload.divisions:
        rows = list_division_groups()
        configured: dict[str, list[str]] = {}
        for row in rows:
            configured.setdefault(row["division"], []).append(row["assignee_group"])

        unknown = [division for division in payload.divisions if division not in configured]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown or inactive divisions: {', '.join(unknown)}",
            )
        for division in payload.divisions:
            selected.extend(configured[division])
    return list(dict.fromkeys(selected))


def _resolve_statuses(payload: RawReportRequest) -> list[str] | None:
    """Preserve an unscoped status query or add the canonical closed statuses."""
    if payload.statuses is None:
        return None
    selected = list(payload.statuses)
    if payload.include_closed:
        selected.extend(sorted(CLOSED_STATUSES))
    return list(dict.fromkeys(selected))


def create_raw_report(payload: RawReportRequest, request: Request):
    """Query Helix directly without applying daily-report business rules."""
    extractor = HelixExtractor()
    if not extractor.is_configured():
        raise HTTPException(status_code=503, detail="Helix connection is not configured")

    selected_fields = payload.fields or list(HELIX_FIELD_MAP.values())
    selected_groups = _resolve_assignee_groups(payload)
    selected_statuses = _resolve_statuses(payload)
    try:
        rows = extractor.extract_raw_report(
            start_date=payload.start,
            end_date=payload.end,
            date_field=payload.date_field,
            fields=selected_fields,
            assignee_groups=selected_groups,
            assignees=payload.assignees,
            statuses=selected_statuses,
            categories=payload.categories,
            request_ids=payload.request_ids,
            task_ids=payload.task_ids,
            calculate_sla=payload.calculate_sla,
            max_records=payload.limit,
        )
    except requests.RequestException as exc:
        user = getattr(request.state, "current_user", None)
        audit_event(
            "generate_helix_raw_report",
            "helix_raw_report",
            actor=getattr(user, "email", None),
            request=request,
            result="FAILED",
            details={
                "date_field": payload.date_field,
                "limit": payload.limit,
                "calculate_sla": payload.calculate_sla,
                "include_closed": payload.include_closed,
            },
        )
        raise HTTPException(status_code=502, detail=f"Helix raw report request failed: {exc}") from exc

    user = getattr(request.state, "current_user", None)
    audit_event(
        "generate_helix_raw_report",
        "helix_raw_report",
        actor=getattr(user, "email", None),
        request=request,
        details={
            "date_field": payload.date_field,
            "start": payload.start.isoformat() if payload.start else None,
            "end": payload.end.isoformat() if payload.end else None,
            "division_count": len(payload.divisions or []),
            "assignee_group_count": len(selected_groups),
            "assignee_count": len(payload.assignees or []),
            "record_count": len(rows),
            "calculate_sla": payload.calculate_sla,
            "include_closed": payload.include_closed,
            "limit": payload.limit,
        },
    )

    return {
        "source": "helix:TMS:Task",
        "start": payload.start,
        "end": payload.end,
        "date_field": payload.date_field,
        "fields": selected_fields + (
            ["report_category", "sla_status", "hours_open", "sla_calculated_at"]
            if payload.calculate_sla else []
        ),
        "divisions": payload.divisions or [],
        "assignee_groups": selected_groups,
        "assignees": payload.assignees or [],
        "statuses": selected_statuses or [],
        "all_statuses": selected_statuses is None,
        "include_closed": payload.include_closed or selected_statuses is None,
        "categories": payload.categories or [],
        "request_ids": payload.request_ids or [],
        "task_ids": payload.task_ids or [],
        "calculate_sla": payload.calculate_sla,
        "sla_calculated_at": (
            rows[0].get("sla_calculated_at") if payload.calculate_sla and rows else None
        ),
        "count": len(rows),
        "limit": payload.limit,
        "limit_reached": len(rows) >= payload.limit,
        "records": rows,
    }
