"""Mapping of Helix AR entries into canonical pipeline records."""

import logging

from helix.config import HELIX_FIELD_MAP
from helix.datetime_utils import parse_helix_datetime
from pipeline.models import ChangeRecord

logger = logging.getLogger(__name__)


class HelixTaskMapper:
    @staticmethod
    def change_schedule(values: dict):
        return (
            parse_helix_datetime(values.get("Scheduled Start Date")),
            parse_helix_datetime(values.get("Scheduled End Date")),
        )

    @staticmethod
    def record(entry: dict) -> ChangeRecord | None:
        values = entry.get("values", {})
        row = {
            canonical: values.get(source)
            for source, canonical in HELIX_FIELD_MAP.items()
        }
        request_id = str(row.get("request_id") or "").strip()
        if not request_id:
            return None

        def clean(value):
            text = str(value or "").strip()
            return text or None

        return ChangeRecord(
            request_id=request_id,
            task_id=str(row.get("task_id") or "").strip(),
            op_cat_tier1=clean(row.get("op_cat_tier1")),
            summary=clean(row.get("summary")),
            assignee=clean(row.get("assignee")),
            priority=clean(row.get("priority")),
            status=clean(row.get("status")),
            status_reason=clean(row.get("status_reason")),
            assignee_group=clean(row.get("assignee_group")),
            notes=clean(row.get("notes")),
            create_date=parse_helix_datetime(row.get("create_date")),
            assign_time=parse_helix_datetime(row.get("assign_time")),
            closed_time=parse_helix_datetime(row.get("closed_time")),
            scheduled_start=parse_helix_datetime(row.get("scheduled_start")),
            scheduled_end=parse_helix_datetime(row.get("scheduled_end")),
            source="helix_api",
            raw_payload=values,
        )

