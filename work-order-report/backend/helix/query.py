"""AR System qualification construction."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from helix.config import (
    DATE_FIELD,
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

    def task_query(
        self, *, groups: list[str], statuses: list[str],
        since: datetime | None = None,
        start_date: datetime | date | str | None = None,
        end_date: datetime | date | str | None = None,
    ) -> str:
        clauses = []
        if groups:
            clauses.append(
                f"({' OR '.join(self.equals('Assignee Group', item) for item in groups)})"
            )
        if statuses:
            clauses.append(
                f"({' OR '.join(self.equals('Status', item) for item in statuses)})"
            )
        if start_date:
            clauses.append(
                f"'{DATE_FIELD}' >= {format_helix_timestamp(start_date)}"
            )
        elif since:
            clauses.append(f"'{DATE_FIELD}' >= {format_helix_timestamp(since)}")
        if end_date:
            clauses.append(
                f"'{DATE_FIELD}' <= "
                f"{format_helix_timestamp(end_date, end_of_day=True)}"
            )
        return " AND ".join(clauses)

    def closures(
        self, groups: list[str]
    ) -> tuple[str, datetime, datetime]:
        local_now = datetime.now(ZoneInfo(WORKSPACE_TIMEZONE))
        window_end = local_now.replace(
            hour=PIPELINE_SCHEDULE_HOUR, minute=0, second=0, microsecond=0
        )
        if local_now < window_end:
            window_end -= timedelta(days=1)
        window_start = window_end - timedelta(days=1)
        clauses = []
        if groups:
            clauses.append(
                f"({' OR '.join(self.equals('Assignee Group', item) for item in groups)})"
            )
        clauses.extend([
            f"'Actual End Date' >= {format_helix_timestamp(window_start)}",
            f"'Actual End Date' < {format_helix_timestamp(window_end)}",
        ])
        return " AND ".join(clauses), window_start, window_end

    def successful_closures(
        self, groups: list[str]
    ) -> tuple[str, datetime, datetime]:
        """Backward-compatible success-only closure qualification."""
        query, window_start, window_end = self.closures(groups)
        success = self.equals("StatusReasonSelection", "Success")
        return f"{query} AND {success}", window_start, window_end

    def raw_report(
        self, *, start_date=None, end_date=None, date_field="Create Date",
        groups=None, assignees=None, statuses=None, request_ids=None, task_ids=None,
    ) -> str:
        if date_field not in HELIX_RAW_REPORT_DATE_FIELDS:
            raise ValueError(f"Unsupported Helix date field: {date_field}")
        clauses = []
        for field, values in (
            ("Assignee Group", groups),
            ("Assignee", assignees),
            ("Status", statuses),
            ("RootRequestID", request_ids),
            ("Task ID", task_ids),
        ):
            if values:
                clauses.append(
                    f"({' OR '.join(self.equals(field, value) for value in values)})"
                )
        if start_date is not None:
            clauses.append(
                f"'{date_field}' >= {format_helix_timestamp(start_date)}"
            )
        if end_date is not None:
            clauses.append(
                f"'{date_field}' <= "
                f"{format_helix_timestamp(end_date, end_of_day=True)}"
            )
        return " AND ".join(clauses)
