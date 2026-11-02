"""Helix integration configuration and field contracts."""

import os

from config.mappings import OPEN_STATUSES

HELIX_BASE_URL = os.getenv("HELIX_BASE_URL", "")
HELIX_USERNAME = os.getenv("HELIX_USERNAME") or os.getenv("REMEDY_USERNAME", "")
HELIX_PASSWORD = os.getenv("HELIX_PASSWORD") or os.getenv("REMEDY_PASSWORD", "")

BATCH_SIZE = int(os.getenv("HELIX_BATCH_SIZE", "500"))
PAGE_SIZE = int(os.getenv("HELIX_PAGE_SIZE", "1000"))
MAX_RECORDS = int(os.getenv("HELIX_MAX_RECORDS", "50000"))
DATE_FIELD = os.getenv("HELIX_DATE_FIELD", "Create Date")
ENRICH_CHANGE_SCHEDULES = os.getenv(
    "HELIX_ENRICH_CHANGE_SCHEDULES", "true"
).strip().lower() in ("1", "true", "yes")
CHANGE_LOOKUP_BATCH_SIZE = int(os.getenv("HELIX_CHANGE_LOOKUP_BATCH_SIZE", "50"))
INCLUDE_YESTERDAY_SUCCESS_CLOSURES = os.getenv(
    "HELIX_INCLUDE_YESTERDAY_SUCCESS_CLOSURES", "true"
).strip().lower() in ("1", "true", "yes")
WORKSPACE_TIMEZONE = os.getenv("WORKSPACE_TIMEZONE", "Africa/Johannesburg")
PIPELINE_SCHEDULE_HOUR = int(os.getenv("PIPELINE_SCHEDULE_HOUR", "7"))
VERIFY_SSL = os.getenv("HELIX_VERIFY_SSL", "false").strip().lower() in (
    "1", "true", "yes"
)
REQUEST_SLEEP_SECONDS = float(os.getenv("HELIX_REQUEST_SLEEP_SECONDS", "0.1"))
USE_FIELD_SELECTION = os.getenv(
    "HELIX_USE_FIELD_SELECTION", "false"
).strip().lower() in ("1", "true", "yes")
DEFAULT_STATUSES = ",".join(sorted(OPEN_STATUSES))

HELIX_FIELD_MAP = {
    "RootRequestID": "request_id",
    "Task ID": "task_id",
    "Service Cat Tier 1": "op_cat_tier1",
    "Summary": "summary",
    "Assignee": "assignee",
    "Priority": "priority",
    "Status": "status",
    "Create Date": "create_date",
    "Assign Time": "assign_time",
    "Actual End Date": "closed_time",
    "Scheduled Start Date": "scheduled_start",
    "Scheduled End Date": "scheduled_end",
    "StatusReasonSelection": "status_reason",
    "Assignee Group": "assignee_group",
    "Notes": "notes",
}

HELIX_RAW_REPORT_DATE_FIELDS = frozenset({
    "Create Date",
    "Assign Time",
    "Actual End Date",
    "Scheduled Start Date",
    "Scheduled End Date",
})

CHANGE_FORM = "CHG:Infrastructure Change"
CHANGE_FIELD_MAP = {
    "Infrastructure Change ID": "request_id",
    "Scheduled Start Date": "scheduled_start",
    "Scheduled End Date": "scheduled_end",
}

