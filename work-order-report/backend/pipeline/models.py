"""
pipeline/models.py
==================
Canonical schema for a single Helix Work Order after ingestion.

Every source adapter (Helix API, Excel or CSV export) must produce a list of
WorkOrderRecord objects. Downstream transforms only consume this shape; they
never touch raw source column names.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WorkOrderRecord:
    # ---- identifiers -------------------------------------------------------
    work_order_id:   str                    # Work Order ID (WO...)

    # ---- descriptive -------------------------------------------------------
    summary:         Optional[str] = None
    work_order_type: Optional[str] = None   # Work Order Type
    category_tier1:  Optional[str] = None   # Categorization Tier 1 (fallback type)
    status:          Optional[str] = None
    status_reason:   Optional[str] = None
    priority:        Optional[str] = None   # Critical / High / Medium / Low
    requester:       Optional[str] = None
    support_group:   Optional[str] = None   # Support Group Name
    assignee:        Optional[str] = None   # Request Assignee
    notes:           Optional[str] = None

    # ---- timestamps (workspace-local, naive) --------------------------------
    submit_date:     Optional[datetime] = None
    target_date:     Optional[datetime] = None   # SLA due date
    completed_date:  Optional[datetime] = None
    last_modified:   Optional[datetime] = None

    # ---- extraction context ------------------------------------------------
    source:          str = "helix_api"           # "csv" | "excel" | "helix_api"
    raw_payload:     Optional[dict] = field(default=None)

    # ---- derived (populated by transform layer) ----------------------------
    division:        Optional[str] = field(default=None)
    report_category: Optional[str] = field(default=None)
    sla_status:      Optional[str] = field(default=None)
    hours_open:      Optional[float] = field(default=None)
    days_to_target:  Optional[int] = field(default=None)   # negative = overdue
    is_open:         bool = field(default=False)   # status is in OPEN_STATUSES
    is_excluded:     bool = field(default=False)

    @property
    def priority_normalised(self) -> str:
        if not self.priority:
            return "Medium"
        return self.priority.strip().capitalize()

    def __repr__(self) -> str:
        return (
            f"WorkOrderRecord({self.work_order_id} | type={self.report_category} | "
            f"sla={self.sla_status} | div={self.division} | excl={self.is_excluded})"
        )
