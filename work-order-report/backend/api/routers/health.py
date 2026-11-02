"""
api/routers/health.py
=====================
Health and observability endpoints.

GET /api/v1/health         — API + pipeline status and Work Order counts
GET /api/v1/pipeline-runs  — Recent pipeline run history
"""

from datetime import datetime

from pipeline.db import run_query



def health():
    """
    Returns API status, last pipeline run time, and Work Order totals.
    Used by monitoring to verify data freshness.
    """
    heartbeat_rows = run_query(
        "SELECT last_run_at, last_run_status, updated_at "
        "FROM reporting.pipeline_heartbeat WHERE id = 1"
    )
    counts = run_query(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE is_open AND NOT is_excluded) AS active,
            COUNT(*) FILTER (WHERE is_open AND NOT is_excluded AND sla_status = 'BREACHED') AS breached
        FROM staging.raw_work_orders
        """
    )
    totals = counts[0] if counts else {}
    hb = heartbeat_rows[0] if heartbeat_rows else {}

    return {
        "status": "ok",
        "api_time": datetime.now().isoformat(),
        "pipeline": {
            "last_run_at":     hb.get("last_run_at"),
            "last_run_status": hb.get("last_run_status"),
            "updated_at":      hb.get("updated_at"),
        },
        "work_orders": {
            "total":    totals.get("total", 0) or 0,
            "active":   totals.get("active", 0) or 0,
            "breached": totals.get("breached", 0) or 0,
        },
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
