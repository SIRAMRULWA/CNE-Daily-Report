"""
api/services/record_queries.py
==============================
Shared raw-change query helpers for records and workspace endpoints.
"""

import os
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from pipeline.db import run_query


WORKSPACE_TIMEZONE = os.getenv("WORKSPACE_TIMEZONE", "Africa/Johannesburg")


def _today_filter() -> tuple[str, list[str]]:
    """Restrict live Operations Console data to records loaded today."""
    condition = """
        loaded_at >= (
            date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE %s)
            AT TIME ZONE %s
        )
        AND loaded_at < (
            (date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE %s) + INTERVAL '1 day')
            AT TIME ZONE %s
        )
    """
    return condition, [WORKSPACE_TIMEZONE] * 4


def _workspace_metadata(row_count: int) -> dict:
    now = datetime.now(ZoneInfo(WORKSPACE_TIMEZONE))
    return {
        "as_of": now.isoformat(),
        "data_date": now.date().isoformat(),
        "data_available": row_count > 0,
        "timezone": WORKSPACE_TIMEZONE,
    }


def build_record_filters(
    division: Optional[str] = None,
    assignee_group: Optional[str] = None,
    sla: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    include_excluded: bool = False,
) -> tuple[list[str], list]:
    today_condition, today_params = _today_filter()
    conditions = [today_condition]
    params: list = today_params

    if not include_excluded:
        conditions.append("NOT (exclude_change OR exclude_incident)")

    if division:
        conditions.append("report_group = %s")
        params.append(division)
    if assignee_group:
        conditions.append("assignee_group = %s")
        params.append(assignee_group)
    if sla:
        conditions.append("sla_status = %s")
        params.append(sla)
    if category:
        conditions.append("report_category = %s")
        params.append(category)
    if priority:
        conditions.append("LOWER(priority) = LOWER(%s)")
        params.append(priority)
    if search:
        conditions.append(
            "(request_id ILIKE %s OR task_id ILIKE %s OR summary ILIKE %s OR assignee ILIKE %s)"
        )
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern, pattern])

    return conditions, params


def list_records(
    division: Optional[str] = None,
    assignee_group: Optional[str] = None,
    sla: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    include_excluded: bool = False,
    detailed: bool = True,
    limit: int = 250,
    offset: int = 0,
) -> dict:
    conditions, params = build_record_filters(
        division=division,
        assignee_group=assignee_group,
        sla=sla,
        category=category,
        priority=priority,
        search=search,
        include_excluded=include_excluded,
    )
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.extend([limit, offset])

    detail_columns = """
            CASE
                WHEN report_category = 'CHANGE' AND scheduled_end IS NOT NULL
                    THEN scheduled_end + INTERVAL '30 minutes'
                WHEN report_category IN ('INCIDENT', 'ACCESS', 'EVENT') AND assign_time IS NOT NULL
                    THEN assign_time + INTERVAL '24 hours'
                ELSE NULL
            END AS due_at,
            CASE
                WHEN report_category = 'CHANGE' AND scheduled_end IS NOT NULL
                    THEN EXTRACT(EPOCH FROM ((scheduled_end + INTERVAL '30 minutes') - NOW()))::INT
                WHEN report_category IN ('INCIDENT', 'ACCESS', 'EVENT') AND assign_time IS NOT NULL
                    THEN EXTRACT(EPOCH FROM ((assign_time + INTERVAL '24 hours') - NOW()))::INT
                ELSE NULL
            END AS seconds_to_breach,
    """ if detailed else ""

    rows = run_query(
        f"""
        SELECT
            request_id,
            task_id,
            report_group AS division,
            report_group,
            assignee_group,
            report_category,
            sla_status,
            priority,
            status,
            status_reason,
            assignee,
            summary,
            ROUND(hours_open::NUMERIC, 2) AS hours_open,
            assign_time,
            scheduled_start,
            scheduled_end,
            closed_time,
            {detail_columns}
            exclude_change,
            exclude_incident,
            source,
            loaded_at
        FROM staging.raw_changes
        {where}
        ORDER BY
            CASE sla_status
                WHEN 'BREACHED' THEN 1
                WHEN 'NEARING_SLA' THEN 2
                WHEN 'NO_SCHEDULE' THEN 3
                WHEN 'NO_ASSIGN_TIME' THEN 4
                ELSE 5
            END,
            report_group,
            assignee_group,
            assign_time DESC NULLS LAST
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    )

    total = run_query(
        f"SELECT COUNT(*) AS total FROM staging.raw_changes {where}",
        tuple(params[:-2]) if params[:-2] else None,
    )

    total_records = int(total[0]["total"]) if total else 0
    return {
        **_workspace_metadata(total_records),
        "records": rows,
        "count": len(rows),
        "total": total[0]["total"] if total else 0,
        "limit": limit,
        "offset": offset,
    }


def summarize_records(
    division: Optional[str] = None,
    assignee_group: Optional[str] = None,
    include_excluded: bool = False,
) -> dict:
    conditions, params = build_record_filters(
        division=division,
        assignee_group=assignee_group,
        include_excluded=include_excluded,
    )
    conditions.extend([
        "report_group IS NOT NULL",
        "report_category IN ('INCIDENT','CHANGE','ACCESS','EVENT')",
    ])
    where = "WHERE " + " AND ".join(conditions)

    rows = run_query(
        f"""
        SELECT
            report_group AS division,
            assignee_group,
            sla_status,
            report_category,
            COUNT(*) AS record_count,
            ROUND(AVG(hours_open)::NUMERIC, 2) AS avg_hours_open,
            MAX(loaded_at) AS last_loaded_at
        FROM staging.raw_changes
        {where}
        GROUP BY report_group, assignee_group, sla_status, report_category
        ORDER BY
            report_group,
            assignee_group,
            CASE sla_status
                WHEN 'BREACHED' THEN 1
                WHEN 'NEARING_SLA' THEN 2
                WHEN 'NO_SCHEDULE' THEN 3
                WHEN 'NO_ASSIGN_TIME' THEN 4
                ELSE 5
            END,
            report_category
        """,
        tuple(params) if params else None,
    )

    total_records = sum(int(row["record_count"]) for row in rows)
    return {
        **_workspace_metadata(total_records),
        "rows": rows,
        "count": len(rows),
        "total_records": total_records,
    }


def get_record_by_request_id(request_id: str) -> dict | None:
    rows = run_query(
        """
        SELECT *
        FROM staging.raw_changes
        WHERE request_id = %s
        ORDER BY loaded_at DESC
        LIMIT 1
        """,
        (request_id,),
    )
    return rows[0] if rows else None


def list_excluded_records(limit: int = 200) -> dict:
    rows = run_query(
        """
        SELECT
            request_id,
            task_id,
            report_group,
            report_category,
            sla_status,
            status,
            scheduled_end,
            exclude_change,
            exclude_incident,
            CASE
                WHEN exclude_change AND scheduled_end IS NULL  THEN 'No schedule date'
                WHEN exclude_change AND scheduled_end < NOW() - INTERVAL '90 days'
                    THEN 'Stale change (> 90 days)'
                WHEN exclude_change AND scheduled_end > NOW() + INTERVAL '1 day'
                    THEN 'Scheduled too far in future'
                WHEN exclude_change THEN 'Weekend/holiday exclusion or closed'
                WHEN exclude_incident THEN 'Incident closed or stale'
                ELSE 'Unknown'
            END AS exclusion_reason,
            loaded_at
        FROM staging.raw_changes
        WHERE exclude_change OR exclude_incident
        ORDER BY loaded_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {"records": rows, "count": len(rows)}
