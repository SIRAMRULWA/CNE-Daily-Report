"""
config/mappings.py
==================
Single source of truth for Work Order Report business rules.

Contains:
  - Default division -> support group mappings
  - Work Order status groups
  - SLA (target date) rule settings
  - Division display order

Every value that operations may need to tune is read from the environment so
it can change without a code release. Changing a rule = changing it here.
"""

import os


def _csv_env(name: str, default: str) -> frozenset[str]:
    raw = os.getenv(name, default)
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _flag_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# 1. DEFAULT DIVISION -> SUPPORT GROUP MAPPINGS
#    Seed values only; the live mapping is managed in config.division_groups
#    through the Divisions screen. Replace with the confirmed Work Order teams.
# ---------------------------------------------------------------------------
DEFAULT_DIVISION_GROUPS = {
    "INTSS": [
        "Appl:TSS Operational Support:OSS",
        "Appl:IN TELECOMS:OSS",
        "Appl:IN PPS:OSS",
        "Appl:IN:PPSQA:OSS",
    ],
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
}

# Static fallback used only when database mappings cannot be loaded.
GROUP_PATTERNS = [
    (group, division)
    for division, groups in DEFAULT_DIVISION_GROUPS.items()
    for group in groups
]

# ---------------------------------------------------------------------------
# 2. WORK ORDER STATUS GROUPS
# ---------------------------------------------------------------------------
OPEN_STATUSES = _csv_env(
    "WO_OPEN_STATUSES", "Assigned,Pending,Waiting Approval,Planning,In Progress"
)
CLOSED_STATUSES = _csv_env("WO_CLOSED_STATUSES", "Completed,Closed")
EXCLUDED_STATUSES = _csv_env("WO_EXCLUDED_STATUSES", "Cancelled,Rejected,Draft")

# ---------------------------------------------------------------------------
# 3. SLA (TARGET DATE) RULES
#    Late = the target date has passed (plus the optional grace period).
# ---------------------------------------------------------------------------
NEARING_WINDOW_HOURS = _int_env("WO_NEARING_WINDOW_HOURS", 24)
GRACE_MINUTES = _int_env("WO_GRACE_MINUTES", 0)
DATE_ONLY_END_OF_DAY = _flag_env("WO_DATE_ONLY_END_OF_DAY", True)

OPEN_SLA_STATUSES = ("WITHIN_SLA", "NEARING_SLA", "BREACHED", "NO_TARGET_DATE")
COMPLETED_SLA_STATUSES = ("MET_TARGET", "MISSED_TARGET", "NO_TARGET_DATE")

UNCLASSIFIED_CATEGORY = "Unclassified"

# ---------------------------------------------------------------------------
# 4. PREFERRED DIVISION DISPLAY ORDER
# ---------------------------------------------------------------------------
DIVISION_ORDER = ["INTSS", "NSD", "CDN", "CVDI"]
