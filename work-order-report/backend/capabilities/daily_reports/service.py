"""Application boundary for immutable Daily Report snapshots."""

from datetime import date
from typing import Literal

from capabilities.daily_reports import repository


class DailyReportService:
    """Expose selected-date report use cases independently of HTTP and email."""

    def report_view(
        self,
        report_date: date | None = None,
        period: Literal["day", "week"] = "day",
        division: str | None = None,
        assignee_group: str | None = None,
        include_dates: bool = True,
        date_limit: int = 90,
        include_records: bool = False,
        sla: str | None = None,
        category: str | None = None,
    ) -> dict:
        return repository.daily_report_view(
            report_date=report_date,
            period=period,
            division=division,
            assignee_group=assignee_group,
            include_dates=include_dates,
            date_limit=date_limit,
            include_records=include_records,
            sla=sla,
            category=category,
        )

    def report_records(
        self,
        report_date: date | None = None,
        period: Literal["day", "week"] = "day",
        division: str | None = None,
        assignee_group: str | None = None,
        sla: str | None = None,
        category: str | None = None,
    ) -> dict:
        return repository.daily_report_records(
            report_date=report_date,
            period=period,
            division=division,
            assignee_group=assignee_group,
            sla=sla,
            category=category,
        )

    def email_data(
        self, report_date: date, division: str, assignee_group: str | None
    ) -> tuple[list[dict], list[dict]]:
        return repository.email_report_data(
            report_date, division, assignee_group
        )


_service = DailyReportService()


def daily_report_view(**kwargs) -> dict:
    return _service.report_view(**kwargs)


def daily_report_records(**kwargs) -> dict:
    return _service.report_records(**kwargs)


def email_report_data(
    report_date: date, division: str, assignee_group: str | None
) -> tuple[list[dict], list[dict]]:
    return _service.email_data(report_date, division, assignee_group)
