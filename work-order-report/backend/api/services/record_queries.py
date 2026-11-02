"""
api/services/record_queries.py
==============================
Current Work Order queries for the records and workspace endpoints.

Reads staging.raw_work_orders, limited to rows loaded by today's pipeline run,
so these screens show the latest load rather than a frozen snapshot.
"""

import os
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from pipeline.db import run_query


WORKSPACE_TIMEZONE = os.getenv("WORKSPACE_TIMEZONE", "Africa/Johannesburg")

SLA_ORDER_SQL = """CASE sla_status
    WHEN 'BREACHED' THEN 1
    WHEN 'NEARING_SLA' THEN 2
    WHEN 'NO_TARGET_DATE' THEN 3
    WHEN 'WITHIN_SLA' THEN 4
    ELSE 5
END"""


def _today_filter() -> tuple[str, list[str]]:
    """Restrict current data to Work Orders loaded today (workspace time)."""
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
    today_condition, params = _today_filter()
    conditions = [today_condition]

    if not include_excluded:
        conditions.extend(["is_open", "NOT is_excluded"])
    if division:
        conditions.append("division = %s")
        params.append(division)
    if assignee_group:
        conditions.append("support_group = %s")
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
            "(work_order_id ILIKE %s OR summary ILIKE %s OR assignee ILIKE %s OR requester ILIKE %s)"
        )
        pattern = f"%{search}%"
        params.extend([pattern] * 4)

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
    where = "WHERE " + " AND ".join(conditions)

    detail_columns = """
            target_date AS due_at,
            CASE WHEN target_date IS NOT NULL
                THEN EXTRACT(EPOCH FROM (
                    target_date - (CURRENT_TIMESTAMP AT TIME ZONE %s)
                ))::INT
            END AS seconds_to_breach,
    """ if detailed else ""
    detail_params = [WORKSPACE_TIMEZONE] if detailed else []

    rows = run_query(
        f"""
        SELECT
            work_order_id,
            division,
            support_group,
            support_group AS assignee_group,
            report_category,
            sla_status,
            priority,
            status,
            status_reason,
            requester,
            assignee,
            summary,
            ROUND(hours_open::NUMERIC, 2) AS hours_open,
            days_to_target,
            submit_date,
            target_date,
            completed_date,
            {detail_columns}
            is_open,
            is_excluded,
            source,
            loaded_at
        FROM staging.raw_work_orders
        {where}
        ORDER BY {SLA_ORDER_SQL}, days_to_target NULLS LAST, division, support_group
        LIMIT %s OFFSET %s
        """,
        tuple(detail_params + params + [limit, offset]),
    )
    total = run_query(
        f"SELECT COUNT(*) AS total FROM staging.raw_work_orders {where}",
        tuple(params),
    )
    total_records = int(total[0]["total"]) if total else 0
    return {
        **_workspace_metadata(total_records),
        "records": rows,
        "count": len(rows),
        "total": total_records,
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
    conditions.append("division IS NOT NULL")
    where = "WHERE " + " AND ".join(conditions)

    rows = run_query(
        f"""
        SELECT
            division,
            support_group,
            support_group AS assignee_group,
            sla_status,
            report_category,
            COUNT(*) AS record_count,
            ROUND(AVG(hours_open)::NUMERIC, 2) AS avg_hours_open,
            MAX(loaded_at) AS last_loaded_at
        FROM staging.raw_work_orders
        {where}
        GROUP BY division, support_group, sla_status, report_category
        ORDER BY division, support_group, {SLA_ORDER_SQL}, report_category
        """,
        tuple(params),
    )
    total_records = sum(int(row["record_count"]) for row in rows)
    return {
        **_workspace_metadata(total_records),
        "rows": rows,
        "count": len(rows),
        "total_records": total_records,
    }
