"""PostgreSQL snapshot queries and established response assembly.

This adapter serves the daily report matrix for every configured division.
Records are included when the pipeline classified them into a division from the
database-managed assignee-group mappings and they are not excluded.
"""

import logging
import os
from datetime import date, datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pipeline.db import run_query

logger = logging.getLogger(__name__)
REPORT_TIMEZONE = os.getenv("WORKSPACE_TIMEZONE", "Africa/Johannesburg")

ACTIVE_SUMMARY_SCOPE_SQL = """EXISTS (
    SELECT 1 FROM config.division_groups configured
    WHERE configured.division = reporting.daily_report_summary.report_group
      AND configured.assignee_group = reporting.daily_report_summary.assignee_group
      AND configured.active
      AND NOT configured.deleted
)"""

ACTIVE_RECORD_SCOPE_SQL = """EXISTS (
    SELECT 1 FROM config.division_groups configured
    WHERE configured.division = reporting.daily_report_records.report_group
      AND configured.assignee_group = reporting.daily_report_records.assignee_group
      AND configured.active
      AND NOT configured.deleted
)"""

EMAIL_RECORD_COLUMNS = [
    "sla_status", "request_id", "task_id", "report_category", "priority",
    "status", "assignee_group", "assignee", "hours_open", "create_date",
    "assign_time", "scheduled_start", "scheduled_end", "summary",
]
CLOSED_CHANGE_COLUMNS = EMAIL_RECORD_COLUMNS + ["status_reason", "closed_time"]


def _division_filter(division: str | None) -> str | None:
    return (division or "").strip() or None


def _date_window(target_date: date | None, period: Literal["day", "week"]) -> tuple[date, date, date]:
    selected_date = target_date or datetime.now(ZoneInfo(REPORT_TIMEZONE)).date()
    if period == "week":
        start_date = selected_date - timedelta(days=selected_date.weekday())
        end_date = start_date + timedelta(days=6)
        return selected_date, start_date, end_date
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


def _summary_rows(
    start_date: date,
    end_date: date,
    selected_division: str | None = None,
    assignee_group: str | None = None,
) -> list[dict]:
    filters = []
    params: list = [start_date, end_date]
    if selected_division:
        filters.append("report_group = %s")
        params.append(selected_division)
    if assignee_group:
        filters.append("assignee_group = %s")
        params.append(assignee_group)

    filter_sql = ""
    if filters:
        filter_sql = "AND " + " AND ".join(filters)

    return run_query(
        f"""
        SELECT
            MIN(report_date) AS report_date,
            report_group AS division,
            report_group,
            assignee_group,
            sla_band,
            COALESCE(SUM(incident_count), 0) AS incident_count,
            COALESCE(SUM(change_count), 0) AS change_count,
            COALESCE(SUM(access_count), 0) AS access_count,
            COALESCE(SUM(event_count), 0) AS event_count,
            COALESCE(SUM(total_count), 0) AS total_count
        FROM reporting.daily_report_summary
        WHERE report_date BETWEEN %s AND %s
          AND {ACTIVE_SUMMARY_SCOPE_SQL}
          {filter_sql}
        GROUP BY report_group, assignee_group, sla_band
        ORDER BY
            report_group,
            assignee_group,
            CASE sla_band
                WHEN 'Total Open Calls' THEN 1
                WHEN 'Calls Nearing SLA' THEN 2
                WHEN 'Breached Calls' THEN 3
                ELSE 99
            END
        """,
        tuple(params),
    )


def _kpi_payload(
    selected_date: date,
    start_date: date,
    end_date: date,
    period: str,
    selected_division: str | None = None,
    assignee_group: str | None = None,
) -> dict:
    filters = []
    base_params: list = [start_date, end_date]
    if selected_division:
        filters.append("report_group = %s")
        base_params.append(selected_division)
    if assignee_group:
        filters.append("assignee_group = %s")
        base_params.append(assignee_group)

    filter_sql = ""
    if filters:
        filter_sql = "AND " + " AND ".join(filters)
    base_params_tuple = tuple(base_params)

    rows = run_query(
        f"""
        SELECT
            COALESCE(SUM(incident_count), 0) AS total_incidents,
            COALESCE(SUM(change_count), 0) AS total_changes,
            COALESCE(SUM(access_count), 0) AS total_access,
            COALESCE(SUM(event_count), 0) AS total_events,
            COALESCE(SUM(total_count), 0) AS total_open
        FROM reporting.daily_report_summary
        WHERE report_date BETWEEN %s AND %s
          AND {ACTIVE_SUMMARY_SCOPE_SQL}
          {filter_sql}
          AND sla_band = 'Total Open Calls'
        """,
        base_params_tuple,
    )

    nearing = run_query(
        f"""
        SELECT COALESCE(SUM(total_count), 0) AS total_nearing
        FROM reporting.daily_report_summary
        WHERE report_date BETWEEN %s AND %s
          AND {ACTIVE_SUMMARY_SCOPE_SQL}
          {filter_sql}
          AND sla_band = 'Calls Nearing SLA'
        """,
        base_params_tuple,
    )

    breached = run_query(
        f"""
        SELECT COALESCE(SUM(total_count), 0) AS total_breached
        FROM reporting.daily_report_summary
        WHERE report_date BETWEEN %s AND %s
          AND {ACTIVE_SUMMARY_SCOPE_SQL}
          {filter_sql}
          AND sla_band = 'Breached Calls'
        """,
        base_params_tuple,
    )

    successful_closures = run_query(
        f"""
        SELECT
            COALESCE(SUM(total_count), 0) AS total_closed_success_yesterday,
            COALESCE(SUM(incident_count), 0) AS closed_incidents,
            COALESCE(SUM(change_count), 0) AS closed_changes,
            COALESCE(SUM(access_count), 0) AS closed_access,
            COALESCE(SUM(event_count), 0) AS closed_events
        FROM reporting.daily_report_success_closures
        WHERE report_date BETWEEN %s AND %s
          {filter_sql}
        """,
        base_params_tuple,
    )

    closure_groups = run_query(
        f"""
        SELECT
            report_group AS division,
            assignee_group,
            MIN(closure_date) AS closure_date,
            MIN(window_start) AS window_start,
            MAX(window_end) AS window_end,
            COALESCE(SUM(total_count), 0) AS total_closed_success
        FROM reporting.daily_report_success_closures
        WHERE report_date BETWEEN %s AND %s
          {filter_sql}
        GROUP BY report_group, assignee_group
        ORDER BY report_group, assignee_group
        """,
        base_params_tuple,
    )

    division_rows = run_query(
        f"""
        SELECT
            report_group AS division,
            COALESCE(SUM(total_count) FILTER (WHERE sla_band = 'Total Open Calls'), 0) AS total_open,
            COALESCE(SUM(total_count) FILTER (WHERE sla_band = 'Calls Nearing SLA'), 0) AS total_nearing,
            COALESCE(SUM(total_count) FILTER (WHERE sla_band = 'Breached Calls'), 0) AS total_breached
        FROM reporting.daily_report_summary
        WHERE report_date BETWEEN %s AND %s
          AND {ACTIVE_SUMMARY_SCOPE_SQL}
        GROUP BY report_group
        ORDER BY report_group
        """,
        (start_date, end_date),
    )

    kpis = rows[0] if rows else {}
    kpis["total_nearing"] = (nearing[0]["total_nearing"] if nearing else 0) or 0
    kpis["total_breached"] = (breached[0]["total_breached"] if breached else 0) or 0
    closure_kpis = successful_closures[0] if successful_closures else {}
    kpis["total_closed_success_yesterday"] = (
        closure_kpis.get("total_closed_success_yesterday", 0) or 0
    )
    kpis["closed_incidents"] = closure_kpis.get("closed_incidents", 0) or 0
    kpis["closed_changes"] = closure_kpis.get("closed_changes", 0) or 0
    kpis["closed_access"] = closure_kpis.get("closed_access", 0) or 0
    kpis["closed_events"] = closure_kpis.get("closed_events", 0) or 0
    kpis["successful_closures_by_group"] = closure_groups
    kpis.update(_date_response(selected_date, start_date, end_date, period))
    kpis["division"] = selected_division
    kpis["assignee_group"] = assignee_group
    kpis["divisions"] = division_rows
    return kpis


def _available_dates(limit: int = 90) -> list[dict]:
    return run_query(
        f"""
        SELECT
            report_date,
            COUNT(DISTINCT report_group) AS division_count,
            COUNT(DISTINCT assignee_group) AS assignee_group_count,
            COALESCE(SUM(total_count) FILTER (WHERE sla_band = 'Total Open Calls'), 0) AS total_open
        FROM reporting.daily_report_summary
        WHERE {ACTIVE_SUMMARY_SCOPE_SQL}
        GROUP BY report_date
        ORDER BY report_date DESC
        LIMIT %s
        """,
        (limit,),
    )


def _daily_report_groups(
    start_date: date,
    end_date: date,
    selected_division: str | None = None,
    assignee_group: str | None = None,
) -> list[dict]:
    filters = ["report_date BETWEEN %s AND %s"]
    params: list = [start_date, end_date]
    if selected_division:
        filters.append("report_group = %s")
        params.append(selected_division)
    if assignee_group:
        filters.append("assignee_group = %s")
        params.append(assignee_group)

    where = " AND ".join(filters)

    return run_query(
        f"""
        SELECT
            report_group,
            COUNT(DISTINCT request_id || ':' || task_id) AS active_records,
            COUNT(DISTINCT assignee_group) AS assignee_group_count,
            ARRAY_AGG(DISTINCT assignee_group ORDER BY assignee_group) AS assignee_groups
        FROM reporting.daily_report_records
        WHERE {where}
          AND {ACTIVE_RECORD_SCOPE_SQL}
        GROUP BY report_group
        ORDER BY report_group
        """,
        tuple(params),
    )


def _report_records(
    start_date: date,
    end_date: date,
    selected_division: str | None = None,
    assignee_group: str | None = None,
    sla: str | None = None,
    category: str | None = None,
) -> dict:
    conditions = ["report_date BETWEEN %s AND %s"]
    params: list = [start_date, end_date]

    if selected_division:
        conditions.append("report_group = %s")
        params.append(selected_division)
    if assignee_group:
        conditions.append("assignee_group = %s")
        params.append(assignee_group)
    if sla:
        conditions.append("sla_status = %s")
        params.append(sla)
    if category:
        conditions.append("report_category = %s")
        params.append(category)

    where = " AND ".join(conditions)

    rows = run_query(
        f"""
        SELECT
            report_date,
            request_id,
            task_id,
            report_group,
            report_category,
            sla_status,
            priority,
            status,
            assignee,
            assignee_group,
            summary,
            ROUND(hours_open::NUMERIC, 1) AS hours_open,
            scheduled_end,
            assign_time,
            loaded_at,
            snapshotted_at
        FROM reporting.daily_report_records
        WHERE {where}
          AND {ACTIVE_RECORD_SCOPE_SQL}
        ORDER BY
            report_date DESC,
            CASE sla_status
                WHEN 'BREACHED' THEN 1
                WHEN 'NEARING_SLA' THEN 2
                WHEN 'NO_SCHEDULE' THEN 3
                WHEN 'NO_ASSIGN_TIME' THEN 4
                ELSE 5
            END,
            report_group,
            assignee_group,
            report_category
        """,
        tuple(params) if params else None,
    )

    return {
        "as_of": datetime.now().isoformat(),
        "scope": "historical_report_snapshot",
        "date_from": str(start_date),
        "date_to": str(end_date),
        "records": rows,
        "count": len(rows),
        "filters": {
            "division": selected_division,
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
    """
    One-call daily report screen payload for the frontend.

    Use this as the primary endpoint for report pages.
    """
    selected_date, start_date, end_date = _date_window(report_date, period)
    selected_division = _division_filter(division)

    payload = {
        **_date_response(selected_date, start_date, end_date, period),
        "filters": {
            "division": selected_division,
            "assignee_group": assignee_group,
        },
        "kpis": _kpi_payload(
            selected_date=selected_date,
            start_date=start_date,
            end_date=end_date,
            period=period,
            selected_division=selected_division,
            assignee_group=assignee_group,
        ),
        "summary": {
            "rows": _summary_rows(
                start_date=start_date,
                end_date=end_date,
                selected_division=selected_division,
                assignee_group=assignee_group,
            ),
        },
        "groups": _daily_report_groups(
            start_date=start_date,
            end_date=end_date,
            selected_division=selected_division,
            assignee_group=assignee_group,
        ),
    }
    payload["summary"]["count"] = len(payload["summary"]["rows"])
    payload["data_available"] = payload["summary"]["count"] > 0

    if include_dates:
        dates = _available_dates(limit=date_limit)
        payload["available_dates"] = {"dates": dates, "count": len(dates), "limit": date_limit}

    if include_records:
        records = _report_records(
            start_date=start_date,
            end_date=end_date,
            selected_division=selected_division,
            assignee_group=assignee_group,
            sla=sla,
            category=category,
        )
        payload["records"] = records

    return payload


def daily_report_records(
    report_date: Optional[date] = None,
    period: Literal["day", "week"] = "day",
    division: Optional[str] = None,
    assignee_group: Optional[str] = None,
    sla: Optional[str] = None,
    category: Optional[str] = None,
):
    """
    Historical report records for the selected report date/window.
    """
    selected_date, start_date, end_date = _date_window(report_date, period)
    selected_division = _division_filter(division)
    records = _report_records(
        start_date=start_date,
        end_date=end_date,
        selected_division=selected_division,
        assignee_group=assignee_group,
        sla=sla,
        category=category,
    )
    records.update(_date_response(selected_date, start_date, end_date, period))
    return records


def email_report_data(
    report_date: date,
    division: str,
    assignee_group: str | None,
) -> tuple[list[dict], list[dict]]:
    """Return one immutable snapshot for email rendering and attachments."""
    extra = " AND assignee_group = %s" if assignee_group else ""
    params = (
        (report_date, division, assignee_group)
        if assignee_group
        else (report_date, division)
    )
    summary = run_query(
        f"""SELECT assignee_group, sla_band, incident_count, change_count,
                   access_count, event_count, total_count
            FROM reporting.daily_report_summary
            WHERE report_date = %s AND report_group = %s {extra}
              AND {ACTIVE_SUMMARY_SCOPE_SQL}
            ORDER BY assignee_group,
                CASE sla_band
                    WHEN 'Total Open Calls' THEN 1
                    WHEN 'Calls Nearing SLA' THEN 2
                    WHEN 'Breached Calls' THEN 3
                    ELSE 9
                END""",
        params,
    )
    summary.extend(
        run_query(
            f"""SELECT assignee_group,
                       'Closed Successfully Yesterday' AS sla_band,
                       incident_count, change_count, access_count, event_count,
                       total_count, closure_date, window_start, window_end
                FROM reporting.daily_report_success_closures
                WHERE report_date = %s AND report_group = %s {extra}
                ORDER BY assignee_group""",
            params,
        )
    )
    records = run_query(
        f"""SELECT {', '.join(EMAIL_RECORD_COLUMNS)}
            FROM reporting.daily_report_records
            WHERE report_date = %s AND report_group = %s {extra}
              AND {ACTIVE_RECORD_SCOPE_SQL}
            ORDER BY
                CASE sla_status
                    WHEN 'BREACHED' THEN 1
                    WHEN 'NEARING_SLA' THEN 2
                    ELSE 3
                END,
                assignee_group, request_id, task_id""",
        params,
    )
    return summary, records


def email_closed_changes(
    report_date: date, division: str, assignee_group: str | None,
) -> list[dict]:
    """Return all prior-window closed changes for the attachment-only sheet."""
    extra = " AND assignee_group = %s" if assignee_group else ""
    params = ((report_date, division, assignee_group) if assignee_group
              else (report_date, division))
    return run_query(
        f"""SELECT {', '.join(CLOSED_CHANGE_COLUMNS)}
            FROM reporting.daily_report_closed_changes
            WHERE report_date = %s AND report_group = %s {extra}
            ORDER BY assignee_group, closed_time, request_id, task_id""",
        params,
    )
