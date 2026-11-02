"""
config/mappings.py
==================
Single source of truth for all ITIL Group Reports business logic constants.

Contains:
  - AssigneeGroup â†’ Report Group mapping
  - OpCatTier1   â†’ Report Category mapping
  - RequestID prefix â†’ fallback category
  - SLA thresholds by priority
  - Delete/filter rule parameters
  - Closed/open status sets
  - SA public holidays
  - Report slice definitions

Changing a rule = changing it here. Nothing else.
"""

# ---------------------------------------------------------------------------
# 1. ASSIGNEE GROUP â†’ REPORT GROUP
#    Pattern matching (substring), not exact equality.
#    Order matters â€” first match wins.
# ---------------------------------------------------------------------------
GROUP_PATTERNS = [
    ("Appl:TSS Operational Support:OSS", "INTSS"),
    ("Appl:IN TELECOMS:OSS",        "INTSS"),
    ("Appl:IN PPS:OSS",             "INTSS"),
    ("Appl:IN:PPSQA:OSS",           "INTSS"),
]

INTSS_DAILY_ASSIGNEE_GROUPS = [
    "Appl:TSS Operational Support:OSS",
    "Appl:IN TELECOMS:OSS",
    "Appl:IN PPS:OSS",
    "Appl:IN:PPSQA:OSS",
]

DEFAULT_DIVISION_GROUPS = {
    "NSD": [
        "Appl:VAS SMS:OSS",
        "Appl:VAS MMS:OSS",
        "Appl:VAS Fusion:OSS",
        "Appl:VAS CUR: OSS",
        "Appl:NSD-BSS",
        "Appl:VAS VOICE:OSS",
        "Appl:ESPS:OSS",
        "Appl:IVR:TECHNOTREE:ISO",
        "Appl:LIMS Support",
    ],
    "CDN": [
        "TRANSPORT:CDN",
        "TRANSPORT:CDN NORTH",
        "TRANSPORT: CDN SOUTH",
        "TRANSPORT:CDN SECURITY",
    ],
    "CVDI": [
        "CORE: NEXT GENERATION",
        "CORE:ANCILLARY SYSTEMS",
        "CORE:Core Regional Support and Maintenance:CVD",
        "CORE:Standby CONFIGURATION GROUP:NMG",
        "CORE:Support and Resilience",
        "NMG CS Configuration Group:NMG",
        "CORE:Voice Systems",
        "PSCore",
        "Appl:DATA PACKET CORE:OSS",
    ],
    "INTSS": [
        "Appl:TSS Operational Support:OSS",
        "Appl:IN TELECOMS:OSS",
        "Appl:IN PPS:OSS",
        "Appl:IN:PPSQA:OSS",
        "Change Mngt:IT EIT",
    ],
}

# ---------------------------------------------------------------------------
# 2. OPERATIONAL CATEGORY â†’ REPORT CATEGORY
#    OpCatTier1 â†’ INCIDENT / CHANGE / ACCESS / EVENT
# ---------------------------------------------------------------------------
CATEGORY_MAP = {
    "FAULTS":   "INCIDENT",
    "CHANGE":   "CHANGE",
    "SECURITY": "ACCESS",
    "ACCESS":   "ACCESS",
    "ALARM":    "EVENT",
    "FAILURE":  "EVENT",
}

# RootRequestID prefix fallback task type when OpCatTier1 is blank.
# INC is handled in transform.py because Summary/Notes decide whether it is
# Security, Alarm, or Faults.
REQUEST_PREFIX_TASK_TYPE = {
    "CRQ": "CHANGE",
    "WO": "WORK ORDER",
    "PBI": "PBI",
}

EXCLUDED_OPERATIONAL_CATEGORIES = frozenset({
    "WORK ORDER",
    "WORKORDER",
    "PBI",
})

EXCLUDED_REQUEST_PREFIXES = ("WO", "PBI")

# Assignees whose records must never appear in operational reports.
# Matching is case-insensitive and ignores surrounding whitespace.
EXCLUDED_ASSIGNEES = frozenset({
    "LEONORA DE KOCK",
})

# Work orders assigned to these group patterns are always excluded, even when
# their operational category is Security.
EXCLUDED_WORK_ORDER_GROUP_PATTERNS = (
    "TSS",
)

# ---------------------------------------------------------------------------
# 3. SLA THRESHOLDS
#    Matches the existing INTSS SQL scripts.
# ---------------------------------------------------------------------------
ASSIGN_TIME_NEARING_SECONDS = 79_200
ASSIGN_TIME_BREACH_SECONDS = 86_400
CHANGE_SCHEDULE_GRACE_SECONDS = 1_800
CHANGE_NEARING_WINDOW_SECONDS = 7_200

# ---------------------------------------------------------------------------
# 4. STATUS SETS
# ---------------------------------------------------------------------------
CLOSED_STATUSES = frozenset({
    "Closed", "Cancelled", "Success", "Bypassed"
})

OPEN_STATUSES = frozenset({
    "Assigned", "Staged", "Work In Progress", "Work in Progress", "Pending",
})

# ---------------------------------------------------------------------------
# 5. DELETE / EXCLUDE RULE PARAMETERS
# ---------------------------------------------------------------------------
CHANGE_FUTURE_DAYS_THRESHOLD  = 1    # Changes scheduled > 1 day away â†’ exclude
CHANGE_STALE_DAYS_THRESHOLD   = 90   # Changes scheduled > 90 days ago and still open â†’ exclude
INCIDENT_STALE_DAYS_THRESHOLD = 30   # Incidents older than 30 days â†’ exclude

# ---------------------------------------------------------------------------
# 6. SA PUBLIC HOLIDAYS (YYYY-MM-DD) â€” update annually
# ---------------------------------------------------------------------------
SA_PUBLIC_HOLIDAYS = frozenset({
    "2026-01-01",  # New Year's Day
    "2026-03-21",  # Human Rights Day
    "2026-04-03",  # Good Friday
    "2026-04-06",  # Family Day
    "2026-04-27",  # Freedom Day
    "2026-05-01",  # Workers' Day
    "2026-06-16",  # Youth Day
    "2026-08-09",  # National Women's Day
    "2026-08-10",  # Women's Day observed
    "2026-09-24",  # Heritage Day
    "2026-12-16",  # Day of Reconciliation
    "2026-12-25",  # Christmas Day
    "2026-12-26",  # Day of Goodwill
})

# ---------------------------------------------------------------------------
# 7. REPORT SLICE DEFINITIONS
#    Used by both the API and the dbt report_scoped model.
#    Each entry defines which AssigneeGroup patterns qualify for a report.
# ---------------------------------------------------------------------------
REPORT_SLICES = {
    "daily_intss": {
        "report_name":  "INTSS Daily Operations Report",
        "report_owner": "INTSS",
        "group_patterns": INTSS_DAILY_ASSIGNEE_GROUPS,
    },
    "weekly_intss": {
        "report_name":  "INTSS Weekly Major Faults Report",
        "report_owner": "INTSS",
        "group_patterns": [
            "IN TELECOMS", "TSS Operational Support", "IN PPS",
        ],
    },
    "cvdi_major_faults": {
        "report_name":  "CVDI Major Faults Report",
        "report_owner": "CVDI",
        "group_patterns": [
            "Core Regional Support", "DATA PACKET CORE",
        ],
    },
}

# ---------------------------------------------------------------------------
# 8. PREFERRED DIVISION DISPLAY ORDER (report matrix rows)
# ---------------------------------------------------------------------------
DIVISION_ORDER = [
    "INTSS", "NSD", "CDN", "CVDI",
]
