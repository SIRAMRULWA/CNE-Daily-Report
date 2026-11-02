"""
api/routers/health.py
=====================
Health and observability endpoints.

GET /api/v1/health         — API + pipeline status and record counts
GET /api/v1/pipeline-runs  — Recent pipeline run history
"""

from datetime import datetime

from pipeline.db import run_query



def health():
    """
    Returns API status, last pipeline run time, and record totals.
    Used by Power BI to verify data freshness before report refresh.
    """
    heartbeat_rows = run_query(
        "SELECT last_run_at, last_run_status, updated_at "
        "FROM reporting.pipeline_heartbeat WHERE id = 1"
    )
    count_rows = run_query(
        "SELECT COUNT(*) AS total FROM staging.raw_changes"
    )
    active_rows = run_query(
        "SELECT COUNT(*) AS active FROM staging.raw_changes "
        "WHERE NOT (exclude_change OR exclude_incident) "
        "AND sla_status NOT IN ('CLOSED')"
    )
    breached_rows = run_query(
        "SELECT COUNT(*) AS breached FROM staging.raw_changes "
        "WHERE sla_status = 'BREACHED' "
        "AND NOT (exclude_change OR exclude_incident)"
    )

    hb = heartbeat_rows[0] if heartbeat_rows else {}
    reminder_table = run_query(
        "SELECT to_regclass('reporting.task_reminder_executions') IS NOT NULL AS exists"
    )
    reminder_status = {"configured": False, "failed_last_24_hours": 0, "last_execution_at": None}
    if reminder_table and reminder_table[0]["exists"]:
        reminder_rows = run_query(
            """SELECT COUNT(*) FILTER (WHERE status='FAILED' AND started_at >= NOW()-INTERVAL '24 hours') AS failed,
                      MAX(started_at) AS last_execution_at
               FROM reporting.task_reminder_executions"""
        )
        reminder_status = {
            "configured": True,
            "failed_last_24_hours": int(reminder_rows[0]["failed"] or 0) if reminder_rows else 0,
            "last_execution_at": reminder_rows[0]["last_execution_at"] if reminder_rows else None,
        }

    return {
        "status": "ok",
        "api_time": datetime.now().isoformat(),
        "pipeline": {
            "last_run_at":     hb.get("last_run_at"),
            "last_run_status": hb.get("last_run_status"),
            "updated_at":      hb.get("updated_at"),
        },
        "records": {
            "total":   count_rows[0]["total"]   if count_rows   else 0,
            "active":  active_rows[0]["active"]  if active_rows  else 0,
            "breached":breached_rows[0]["breached"] if breached_rows else 0,
        },
        "task_reminders": reminder_status,
    }


def run_log(limit: int = 20):
    """
    Returns recent pipeline and manual-entry runs with duration.
    """
    rows = run_query(
        """
        SELECT
            run_id,
            pipeline_name,
            source_entity,
            source_file,
            run_start,
            run_end,
            status,
            rows_extracted,
            rows_loaded,
            rows_rejected,
            environment,
            error_message,
            EXTRACT(EPOCH FROM (COALESCE(run_end, NOW()) - run_start))::INT
                AS duration_seconds
        FROM staging.elt_run_log
        ORDER BY run_start DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {"runs": rows, "count": len(rows)}
