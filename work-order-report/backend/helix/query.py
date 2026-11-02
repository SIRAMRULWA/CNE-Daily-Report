"""AR System qualification construction for WOI:WorkOrder."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from config.mappings import CLOSED_STATUSES
from helix.config import (
    DATE_FIELD,
    FIELD_ASSIGNEE,
    FIELD_COMPLETED_DATE,
    FIELD_STATUS,
    FIELD_SUPPORT_GROUP,
    FIELD_WORK_ORDER_ID,
    HELIX_RAW_REPORT_DATE_FIELDS,
    PIPELINE_SCHEDULE_HOUR,
    WORKSPACE_TIMEZONE,
)
from helix.datetime_utils import format_helix_timestamp


class HelixQueryBuilder:
    @staticmethod
    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def equals(self, field: str, value: str) -> str:
        return f"'{field}' = \"{self.escape(value)}\""

    def any_of(self, field: str, values: list[str]) -> str:
        return f"({' OR '.join(self.equals(field, value) for value in values)})"

    def work_order_query(
        self, *, groups: list[str], statuses: list[str],
        since: datetime | None = None,
        start_date: datetime | date | str | None = None,
        end_date: datetime | date | str | None = None,
    ) -> str:
        """Open Work Orders for the mapped support groups."""
        clauses = []
        if groups:
            clauses.append(self.any_of(FIELD_SUPPORT_GROUP, groups))
        if statuses:
            clauses.append(self.any_of(FIELD_STATUS, statuses))
        if start_date:
            clauses.append(f"'{DATE_FIELD}' >= {format_helix_timestamp(start_date)}")
        elif since:
            clauses.append(f"'{DATE_FIELD}' >= {format_helix_timestamp(since)}")
        if end_date:
            clauses.append(
                f"'{DATE_FIELD}' <= {format_helix_timestamp(end_date, end_of_day=True)}"
            )
        return " AND ".join(clauses)

    @staticmethod
    def completion_window(now: datetime | None = None) -> tuple[datetime, datetime]:
        """The previous scheduled 24 hours: 07:00 yesterday to 07:00 today."""
        local_now = now or datetime.now(ZoneInfo(WORKSPACE_TIMEZONE))
        window_end = local_now.replace(
            hour=PIPELINE_SCHEDULE_HOUR, minute=0, second=0, microsecond=0
        )
        if local_now < window_end:
            window_end -= timedelta(days=1)
        return window_end - timedelta(days=1), window_end

    def completions(
        self, groups: list[str], now: datetime | None = None,
    ) -> tuple[str, datetime, datetime]:
        """Work Orders completed in the previous scheduled window."""
        window_start, window_end = self.completion_window(now)
        clauses = []
        if groups:
            clauses.append(self.any_of(FIELD_SUPPORT_GROUP, groups))
        if CLOSED_STATUSES:
            clauses.append(self.any_of(FIELD_STATUS, sorted(CLOSED_STATUSES)))
        clauses.extend([
            f"'{FIELD_COMPLETED_DATE}' >= {format_helix_timestamp(window_start)}",
            f"'{FIELD_COMPLETED_DATE}' < {format_helix_timestamp(window_end)}",
        ])
        return " AND ".join(clauses), window_start, window_end

    def raw_report(
        self, *, start_date=None, end_date=None, date_field=None,
        groups=None, assignees=None, statuses=None, work_order_ids=None,
    ) -> str:
        date_field = date_field or DATE_FIELD
        if date_field not in HELIX_RAW_REPORT_DATE_FIELDS:
            raise ValueError(f"Unsupported Helix date field: {date_field}")
        clauses = []
        for field, values in (
            (FIELD_SUPPORT_GROUP, groups),
            (FIELD_ASSIGNEE, assignees),
            (FIELD_STATUS, statuses),
            (FIELD_WORK_ORDER_ID, work_order_ids),
        ):
            if values:
                clauses.append(self.any_of(field, values))
        if start_date is not None:
            clauses.append(f"'{date_field}' >= {format_helix_timestamp(start_date)}")
        if end_date is not None:
            clauses.append(
                f"'{date_field}' <= {format_helix_timestamp(end_date, end_of_day=True)}"
            )
        return " AND ".join(clauses)
