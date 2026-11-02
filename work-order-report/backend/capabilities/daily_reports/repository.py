"""PostgreSQL snapshot queries and response assembly for the Work Order report.

Reads only the immutable dbt snapshot tables:
  reporting.wo_report_summary  division x support group x SLA counts
  reporting.wo_report_records  open Work Orders behind those counts
  reporting.wo_completed       Work Orders completed in the previous window

The public filter is still called ``assignee_group`` (the division mapping's
name for a team); in Work Order tables that team is the ``support_group``.
"""

import logging
import os
from datetime import date, datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pipeline.db import run_query

logger = logging.getLogger(__name__)
REPORT_TIMEZONE = os.getenv("WORKSPACE_TIMEZONE", "Africa/Johannesburg")

OPEN_SLA_VALUES = ("WITHIN_SLA", "NEARING_SLA", "BREACHED", "NO_TARGET_DATE")
COMPLETED_SLA_VALUES = ("MET_TARGET", "MISSED_TARGET")


def _active_scope(table: str) -> str:
    """The row's support group is still mapped to its division and active."""
    return f"""EXISTS (
    SELECT 1 FROM config.division_groups configured
    WHERE configured.division = {table}.division
      AND configured.assignee_group = {table}.support_group
      AND configured.active
      AND NOT configured.deleted
)"""


SLA_ORDER_SQL = """CASE sla_status
    WHEN 'BREACHED' THEN 1
    WHEN 'NEARING_SLA' THEN 2
    WHEN 'NO_TARGET_DATE' THEN 3
    WHEN 'WITHIN_SLA' THEN 4
    WHEN 'MISSED_TARGET' THEN 5
    WHEN 'MET_TARGET' THEN 6
    ELSE 9
END"""


def _division_filter(division: str | None) -> str | None:
    return (division or "").strip() or None


def _date_window(target_date: date | None, period: Literal["day", "week"]) -> tuple[date, date, date]:
    selected_date = target_date or datetime.now(ZoneInfo(REPORT_TIMEZONE)).date()
    if period == "week":
        start_date = selected_date - timedelta(days=selected_date.weekday())
        return selected_date, start_date, start_date + timedelta(days=6)
    return selected_date, selected_date, selected_date


def _date_response(selected_date: date, start_date: date, end_date: date, period: str) -> dict:
    current_date = datetime.now(ZoneInfo(REPORT_TIMEZONE)).date()
    return {
        "report_date": str(selected_date),
        "period": period,
        "date_from": str(start_date),
        "date_to": str(end_date),
        "current_date": str(current_date),
        "is_historical": selected_date != current_date,
        "timezone": REPORT_TIMEZONE,
    }


def _scope_filters(
    start_date: date,
    end_date: date,
    division: str | None,
    assignee_group: str | None,
) -> tuple[str, list]:
    conditions = ["report_date BETWEEN %s AND %s"]
    params: list = [start_date, end_date]
    if division:
        conditions.append("division = %s")
        params.append(division)
    if assignee_group:
        conditions.append("support_group = %s")
        params.append(assignee_group)
    return " AND ".join(conditions), params


def _summary_rows(start_date, end_date, division=None, assignee_group=None) -> list[dict]:
    """One grid row per division and support group, with completions joined in."""
    where, params = _scope_filters(start_date, end_date, division, assignee_group)
    return run_query(
        f"""
        WITH open_counts AS (
            SELECT
                division,
                support_group,
                SUM(within_count)::BIGINT    AS within_count,
                SUM(nearing_count)::BIGINT   AS nearing_count,
                SUM(breached_count)::BIGINT  AS breached_count,
                SUM(no_target_count)::BIGINT AS no_target_count,
                SUM(total_open)::BIGINT      AS total_open
            FROM reporting.wo_report_summary
            WHERE {where} AND {_active_scope("reporting.wo_report_summary")}
            GROUP BY division, support_group
        ),
        completed_counts AS (
            SELECT
                division,
                support_group,
                COUNT(*) FILTER (WHERE sla_status = 'MET_TARGET')     AS completed_met,
                COUNT(*) FILTER (WHERE sla_status = 'MISSED_TARGET')  AS completed_missed,
                COUNT(*) FILTER (WHERE sla_status = 'NO_TARGET_DATE') AS completed_no_target,
                COUNT(*)                                              AS completed_total
            FROM reporting.wo_completed
            WHERE {where} AND {_active_scope("reporting.wo_completed")}
            GROUP BY division, support_group
        )
        SELECT
            COALESCE(o.division, c.division)           AS division,
            COALESCE(o.support_group, c.support_group) AS support_group,
            COALESCE(o.support_group, c.support_group) AS assignee_group,
            COALESCE(o.within_count, 0)        AS within_count,
            COALESCE(o.nearing_count, 0)       AS nearing_count,
            COALESCE(o.breached_count, 0)      AS breached_count,
            COALESCE(o.no_target_count, 0)     AS no_target_count,
            COALESCE(o.total_open, 0)          AS total_open,
            COALESCE(c.completed_met, 0)       AS completed_met,
            COALESCE(c.completed_missed, 0)    AS completed_missed,
            COALESCE(c.completed_no_target, 0) AS completed_no_target,
            COALESCE(c.completed_total, 0)     AS completed_total
        FROM open_counts o
        FULL OUTER JOIN completed_counts c
            ON o.division = c.division AND o.support_group = c.support_group
        ORDER BY division, support_group
        """,
        tuple(params + params),
    )


def _kpi_payload(selected_date, start_date, end_date, period, division=None, assignee_group=None) -> dict:
    where, params = _scope_filters(start_date, end_date, division, assignee_group)
    open_totals = run_query(
        f"""
        SELECT
            COALESCE(SUM(total_open), 0)::BIGINT      AS total_open,
            COALESCE(SUM(within_count), 0)::BIGINT    AS total_within,
            COALESCE(SUM(nearing_count), 0)::BIGINT   AS total_nearing,
            COALESCE(SUM(breached_count), 0)::BIGINT  AS total_breached,
            COALESCE(SUM(no_target_count), 0)::BIGINT AS total_no_target
        FROM reporting.wo_report_summary
        WHERE {where} AND {_active_scope("reporting.wo_report_summary")}
        """,
        tuple(params),
    )
    completed = run_query(
        f"""
        SELECT
            COUNT(*)                                              AS completed_total,
            COUNT(*) FILTER (WHERE sla_status = 'MET_TARGET')     AS completed_met,
            COUNT(*) FILTER (WHERE sla_status = 'MISSED_TARGET')  AS completed_missed,
            COUNT(*) FILTER (WHERE sla_status = 'NO_TARGET_DATE') AS completed_no_target,
            MIN(window_start) AS completion_window_start,
            MAX(window_end)   AS completion_window_end
        FROM reporting.wo_completed
        WHERE {where} AND {_active_scope("reporting.wo_completed")}
        """,
        tuple(params),
    )
    division_where, division_params = _scope_filters(start_date, end_date, None, None)
    divisions = run_query(
        f"""
        SELECT
            division,
            COALESCE(SUM(total_open), 0)::BIGINT     AS total_open,
            COALESCE(SUM(nearing_count), 0)::BIGINT  AS total_nearing,
            COALESCE(SUM(breached_count), 0)::BIGINT AS total_breached
        FROM reporting.wo_report_summary
        WHERE {division_where} AND {_active_scope("reporting.wo_report_summary")}
        GROUP BY division
        ORDER BY division
        """,
        tuple(division_params),
    )

    kpis = dict(open_totals[0]) if open_totals else {}
    kpis.update(completed[0] if completed else {})
    kpis.update(_date_response(selected_date, start_date, end_date, period))
    kpis["division"] = division
    kpis["assignee_group"] = assignee_group
    kpis["divisions"] = divisions
    return kpis


def _available_dates(limit: int = 90) -> list[dict]:
    return run_query(
        f"""
        SELECT
            report_date,
            COUNT(DISTINCT division)      AS division_count,
            COUNT(DISTINCT support_group) AS assignee_group_count,
            COALESCE(SUM(total_open), 0)::BIGINT  AS total_open
        FROM reporting.wo_report_summary
        WHERE {_active_scope("reporting.wo_report_summary")}
        GROUP BY report_date
        ORDER BY report_date DESC
        LIMIT %s
        """,
        (limit,),
    )


def _report_groups(start_date, end_date, division=None, assignee_group=None) -> list[dict]:
    where, params = _scope_filters(start_date, end_date, division, assignee_group)
    return run_query(
        f"""
        SELECT
            division,
            COUNT(DISTINCT work_order_id) AS active_records,
            COUNT(DISTINCT support_group) AS assignee_group_count,
            ARRAY_AGG(DISTINCT support_group ORDER BY support_group) AS assignee_groups
        FROM reporting.wo_report_records
        WHERE {where} AND {_active_scope("reporting.wo_report_records")}
        GROUP BY division
        ORDER BY division
        """,
        tuple(params),
    )


RECORD_COLUMNS = """
    report_date,
    work_order_id,
    division,
    support_group,
    support_group AS assignee_group,
    report_category,
    sla_status,
    priority,
    status,
    requester,
    assignee,
    summary,
    ROUND(hours_open::NUMERIC, 1) AS hours_open,
    days_to_target,
    submit_date,
    target_date,
    completed_date
"""


def _report_records(start_date, end_date, division=None, assignee_group=None, sla=None, category=None) -> dict:
    """Records behind the grid. Completed statuses read from wo_completed."""
    where, params = _scope_filters(start_date, end_date, division, assignee_group)
    if category:
        where += " AND report_category = %s"
        params.append(category)

    sources = []
    if sla is None or sla in OPEN_SLA_VALUES:
        sources.append(("reporting.wo_report_records", "open"))
    if sla is None or sla in COMPLETED_SLA_VALUES:
        sources.append(("reporting.wo_completed", "completed"))

    rows: list[dict] = []
    for table, record_set in sources:
        condition = where
        table_params = list(params)
        if sla:
            condition += " AND sla_status = %s"
            table_params.append(sla)
        rows.extend(run_query(
            f"""
            SELECT {RECORD_COLUMNS}, '{record_set}' AS record_set
            FROM {table}
            WHERE {condition} AND {_active_scope(table)}
            ORDER BY report_date DESC, {SLA_ORDER_SQL}, days_to_target NULLS LAST,
                     division, support_group, work_order_id
            """,
            tuple(table_params),
        ))

    return {
        "as_of": datetime.now().isoformat(),
        "scope": "historical_report_snapshot",
        "date_from": str(start_date),
        "date_to": str(end_date),
        "records": rows,
        "count": len(rows),
        "filters": {
            "division": division,
            "assignee_group": assignee_group,
            "sla": sla,
            "category": category,
        },
    }


def daily_report_view(
    report_date: Optional[date] = None,
    period: Literal["day", "week"] = "day",
    division: Optional[str] = None,
    assignee_group: Optional[str] = None,
    include_dates: bool = True,
    date_limit: int = 90,
    include_records: bool = False,
    sla: Optional[str] = None,
    category: Optional[str] = None,
):
    """One-call Work Order report screen payload for the frontend."""
    selected_date, start_date, end_date = _date_window(report_date, period)
    selected_division = _division_filter(division)

    rows = _summary_rows(start_date, end_date, selected_division, assignee_group)
    payload = {
        **_date_response(selected_date, start_date, end_date, period),
        "filters": {"division": selected_division, "assignee_group": assignee_group},
        "kpis": _kpi_payload(
            selected_date, start_date, end_date, period, selected_division, assignee_group,
        ),
        "summary": {"rows": rows, "count": len(rows)},
        "groups": _report_groups(start_date, end_date, selected_division, assignee_group),
        "data_available": len(rows) > 0,
    }

    if include_dates:
        dates = _available_dates(limit=date_limit)
        payload["available_dates"] = {"dates": dates, "count": len(dates), "limit": date_limit}

    if include_records:
        payload["records"] = _report_records(
            start_date, end_date, selected_division, assignee_group, sla, category,
        )
    return payload


def daily_report_records(
    report_date: Optional[date] = None,
    period: Literal["day", "week"] = "day",
    division: Optional[str] = None,
    assignee_group: Optional[str] = None,
    sla: Optional[str] = None,
    category: Optional[str] = None,
):
    """Snapshot records for the selected report date or week."""
    selected_date, start_date, end_date = _date_window(report_date, period)
    records = _report_records(
        start_date, end_date, _division_filter(division), assignee_group, sla, category,
    )
    records.update(_date_response(selected_date, start_date, end_date, period))
    return records
