"""
pipeline/models.py
==================
Canonical schema for a single Helix task record after ingestion.

Every source adapter (Excel extractor today, Helix API tomorrow) must
produce a list of ChangeRecord objects. Downstream transforms only consume
this shape — they never touch raw column names directly.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ChangeRecord:
    # ---- identifiers -------------------------------------------------------
    request_id:      str              # RootRequestID  (CRQ.../INC...)
    task_id:         str              # TaskID         (TAS...)

    # ---- classification (may be blank from source) -------------------------
    op_cat_tier1:    Optional[str]    # Service Cat Tier 1
    assignee_group:  Optional[str]    # Assignee Group

    # ---- descriptive -------------------------------------------------------
    summary:         Optional[str]
    assignee:        Optional[str]
    priority:        Optional[str]    # High / Medium / Low / Critical
    status:          Optional[str]
    status_reason:   Optional[str]

    # ---- timestamps --------------------------------------------------------
    create_date:     Optional[datetime]
    assign_time:     Optional[datetime]
    closed_time:     Optional[datetime]   # Actual End Date
    scheduled_start: Optional[datetime]
    scheduled_end:   Optional[datetime]

    # ---- free text ---------------------------------------------------------
    notes:           Optional[str]

    # ---- extraction context ------------------------------------------------
    source:          str = "csv"          # "csv" | "excel" | "helix_api"
    raw_payload:     Optional[dict] = field(default=None)  # full source row

    # ---- derived (populated by transform layer) ----------------------------
    report_group:    Optional[str] = field(default=None)
    report_category: Optional[str] = field(default=None)
    sla_status:      Optional[str] = field(default=None)
    hours_open:      Optional[float] = field(default=None)
    exclude_change:  bool = field(default=False)
    exclude_incident:bool = field(default=False)

    # ---- convenience -------------------------------------------------------
    @property
    def is_change(self) -> bool:
        return (self.request_id or "").upper().startswith("CRQ")

    @property
    def is_incident(self) -> bool:
        return (self.request_id or "").upper().startswith("INC")

    @property
    def is_excluded(self) -> bool:
        return self.exclude_change or self.exclude_incident

    @property
    def priority_normalised(self) -> str:
        if not self.priority:
            return "Medium"
        return self.priority.strip().capitalize()

    def __repr__(self) -> str:
        return (
            f"ChangeRecord({self.request_id}/{self.task_id} | "
            f"cat={self.report_category} | sla={self.sla_status} | "
            f"grp={self.report_group} | excl={self.is_excluded})"
        )
