"""
api/routers/workspace.py
========================
Flexible web-workspace endpoints for team dashboards and drill-through views.
"""

from typing import Optional

from fastapi import Query
from api.services.record_queries import list_records, summarize_records
from pipeline.activity_log import list_activity



def workspace_records(
    division: Optional[str] = Query(default=None),
    assignee_group: Optional[str] = Query(default=None),
    sla: Optional[str] = Query(default=None, description="WITHIN_SLA|NEARING_SLA|BREACHED|NO_TARGET_DATE"),
    category: Optional[str] = Query(default=None, description="Work Order type"),
    priority: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    include_excluded: bool = Query(default=False),
    limit: int = Query(default=250, le=5000),
    offset: int = Query(default=0, ge=0),
):
    """Current open Work Orders, filterable, for the web UI."""
    return list_records(
        division=division,
        assignee_group=assignee_group,
        sla=sla,
        category=category,
        priority=priority,
        search=search,
        include_excluded=include_excluded,
        detailed=True,
        limit=limit,
        offset=offset,
    )


def workspace_summary(
    division: Optional[str] = Query(default=None),
    assignee_group: Optional[str] = Query(default=None),
    include_excluded: bool = Query(default=False),
):
    """Counts by division, support group, SLA status, and Work Order type."""
    return summarize_records(
        division=division,
        assignee_group=assignee_group,
        include_excluded=include_excluded,
    )


def workspace_activity_log(
    entity_type: Optional[str] = Query(default=None),
    entity_types: Optional[str] = Query(default=None, description="Comma-separated entity types"),
    entity_id_prefix: Optional[str] = Query(default=None),
    actor: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Configuration audit trail for the web UI."""
    parsed_entity_types = (
        [value.strip() for value in entity_types.split(",") if value.strip()]
        if entity_types
        else None
    )
    rows = list_activity(
        entity_type=entity_type,
        entity_types=parsed_entity_types,
        entity_id_prefix=entity_id_prefix,
        actor=actor,
        limit=limit,
        offset=offset,
    )
    return {"logs": rows, "count": len(rows), "limit": limit, "offset": offset}


