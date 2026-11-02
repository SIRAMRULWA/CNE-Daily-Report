"""Helix integration configuration and Work Order field contract.

The Helix field names below are the usual WOI:WorkOrder names. Confirm them
against a sample export; each one can be overridden without a code change.
"""

import os

from config.mappings import OPEN_STATUSES


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


HELIX_BASE_URL = os.getenv("HELIX_BASE_URL", "")
HELIX_USERNAME = os.getenv("HELIX_USERNAME") or os.getenv("REMEDY_USERNAME", "")
HELIX_PASSWORD = os.getenv("HELIX_PASSWORD") or os.getenv("REMEDY_PASSWORD", "")

HELIX_FORM = os.getenv("HELIX_FORM", "WOI:WorkOrder").strip()
BATCH_SIZE = int(os.getenv("HELIX_BATCH_SIZE", "500"))
PAGE_SIZE = int(os.getenv("HELIX_PAGE_SIZE", "1000"))
MAX_RECORDS = int(os.getenv("HELIX_MAX_RECORDS", "50000"))
INCLUDE_YESTERDAY_COMPLETIONS = _flag("HELIX_INCLUDE_YESTERDAY_COMPLETIONS", "true")
WORKSPACE_TIMEZONE = os.getenv("WORKSPACE_TIMEZONE", "Africa/Johannesburg")
PIPELINE_SCHEDULE_HOUR = int(os.getenv("PIPELINE_SCHEDULE_HOUR", "7"))
VERIFY_SSL = _flag("HELIX_VERIFY_SSL", "true")
REQUEST_SLEEP_SECONDS = float(os.getenv("HELIX_REQUEST_SLEEP_SECONDS", "0.1"))
USE_FIELD_SELECTION = _flag("HELIX_USE_FIELD_SELECTION", "false")
DEFAULT_STATUSES = ",".join(sorted(OPEN_STATUSES))

# Source field names (overridable while the Helix contract is confirmed).
FIELD_WORK_ORDER_ID = os.getenv("WO_ID_FIELD", "Work Order ID")
FIELD_SUPPORT_GROUP = os.getenv("WO_SUPPORT_GROUP_FIELD", "Support Group Name")
FIELD_STATUS = os.getenv("WO_STATUS_FIELD", "Status")
FIELD_SUBMIT_DATE = os.getenv("WO_SUBMIT_DATE_FIELD", "Submit Date")
FIELD_TARGET_DATE = os.getenv("WO_TARGET_DATE_FIELD", "Scheduled End Date")
FIELD_COMPLETED_DATE = os.getenv("WO_COMPLETED_DATE_FIELD", "Completed Date")
FIELD_ASSIGNEE = os.getenv("WO_ASSIGNEE_FIELD", "Request Assignee")
DATE_FIELD = os.getenv("HELIX_DATE_FIELD", FIELD_SUBMIT_DATE)

# Helix source field -> canonical WorkOrderRecord attribute.
HELIX_FIELD_MAP = {
    FIELD_WORK_ORDER_ID: "work_order_id",
    "Summary": "summary",
    os.getenv("WO_TYPE_FIELD", "Work Order Type"): "work_order_type",
    os.getenv("WO_CATEGORY_FIELD", "Categorization Tier 1"): "category_tier1",
    FIELD_STATUS: "status",
    "Status Reason": "status_reason",
    "Priority": "priority",
    "Customer First Name": "requester_first_name",
    "Customer Last Name": "requester_last_name",
    FIELD_SUPPORT_GROUP: "support_group",
    FIELD_ASSIGNEE: "assignee",
    "Detailed Description": "notes",
    FIELD_SUBMIT_DATE: "submit_date",
    FIELD_TARGET_DATE: "target_date",
    FIELD_COMPLETED_DATE: "completed_date",
    "Last Modified Date": "last_modified",
}

# Fields a custom Helix report may filter its date range on.
HELIX_RAW_REPORT_DATE_FIELDS = frozenset({
    FIELD_SUBMIT_DATE,
    FIELD_TARGET_DATE,
    FIELD_COMPLETED_DATE,
    "Last Modified Date",
})
