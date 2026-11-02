"""Mapping of Helix WOI:WorkOrder entries into canonical pipeline records."""

import logging

from helix.config import HELIX_FIELD_MAP
from helix.datetime_utils import parse_helix_datetime, parse_target_date
from pipeline.models import WorkOrderRecord

logger = logging.getLogger(__name__)


def _clean(value) -> str | None:
    text = str(value or "").strip()
    return text or None


def requester_name(first, last) -> str | None:
    parts = [part for part in (_clean(first), _clean(last)) if part]
    return " ".join(parts) or None


class HelixWorkOrderMapper:
    @staticmethod
    def record(entry: dict) -> WorkOrderRecord | None:
        values = entry.get("values", {})
        row = {
            canonical: values.get(source)
            for source, canonical in HELIX_FIELD_MAP.items()
        }
        work_order_id = str(row.get("work_order_id") or "").strip()
        if not work_order_id:
            return None

        return WorkOrderRecord(
            work_order_id=work_order_id,
            summary=_clean(row.get("summary")),
            work_order_type=_clean(row.get("work_order_type")),
            category_tier1=_clean(row.get("category_tier1")),
            status=_clean(row.get("status")),
            status_reason=_clean(row.get("status_reason")),
            priority=_clean(row.get("priority")),
            requester=requester_name(
                row.get("requester_first_name"), row.get("requester_last_name")
            ),
            support_group=_clean(row.get("support_group")),
            assignee=_clean(row.get("assignee")),
            notes=_clean(row.get("notes")),
            submit_date=parse_helix_datetime(row.get("submit_date")),
            target_date=parse_target_date(row.get("target_date")),
            completed_date=parse_helix_datetime(row.get("completed_date")),
            last_modified=parse_helix_datetime(row.get("last_modified")),
            source="helix_api",
            raw_payload=values,
        )
