"""Database-free tests for the Daily Report capability boundary."""

import unittest
from datetime import date
from io import BytesIO
from unittest.mock import patch

from openpyxl import load_workbook
from capabilities.daily_reports import repository
from capabilities.daily_reports.service import DailyReportService
from notifications.reports import RECORD_COLUMNS, attachment


class DailyReportCapabilityTests(unittest.TestCase):
    def test_day_window_uses_selected_date_without_historical_fallback(self):
        selected, start, end = repository._date_window(
            date(2026, 7, 13), "day"
        )
        self.assertEqual(date(2026, 7, 13), selected)
        self.assertEqual(selected, start)
        self.assertEqual(selected, end)

    def test_week_window_is_monday_through_sunday(self):
        selected, start, end = repository._date_window(
            date(2026, 7, 15), "week"
        )
        self.assertEqual(date(2026, 7, 13), start)
        self.assertEqual(date(2026, 7, 19), end)
        self.assertEqual(date(2026, 7, 15), selected)

    @patch("capabilities.daily_reports.service.repository.daily_report_view")
    def test_service_delegates_complete_view_contract(self, report_view):
        report_view.return_value = {"data_available": False, "summary": {"rows": []}}
        service = DailyReportService()
        result = service.report_view(
            report_date=date(2026, 7, 13),
            division="INTSS",
            include_records=True,
        )
        self.assertFalse(result["data_available"])
        report_view.assert_called_once_with(
            report_date=date(2026, 7, 13),
            period="day",
            division="INTSS",
            assignee_group=None,
            include_dates=True,
            date_limit=90,
            include_records=True,
            sla=None,
            category=None,
        )

    @patch("capabilities.daily_reports.service.repository.email_report_data")
    def test_email_and_api_use_the_same_snapshot_capability(self, email_data):
        email_data.return_value = ([{"sla_band": "Total Open Calls"}], [{"request_id": "INC1"}])
        summary, records = DailyReportService().email_data(
            date(2026, 7, 13), "INTSS", None
        )
        self.assertEqual("Total Open Calls", summary[0]["sla_band"])
        self.assertEqual("INC1", records[0]["request_id"])

    def test_email_record_columns_match_attachment_contract(self):
        self.assertEqual(RECORD_COLUMNS, repository.EMAIL_RECORD_COLUMNS)

    def test_xlsx_adds_all_closed_changes_without_altering_group_sheet(self):
        open_record = {"request_id": "INC1", "assignee_group": "Team A"}
        closed = {
            "request_id": "CRQ1", "task_id": "TAS1",
            "assignee_group": "Team A", "report_category": "CHANGE",
            "status": "Cancelled", "status_reason": "Unsuccessful",
        }
        file = attachment(
            [open_record], "INTSS", date(2026, 7, 31), "XLSX", [closed]
        )
        workbook = load_workbook(BytesIO(file.content))
        self.assertEqual(["Team A", "Closed Changes"], workbook.sheetnames)
        self.assertEqual("INC1", workbook["Team A"].cell(2, 2).value)
        closed_sheet = workbook["Closed Changes"]
        headers = [cell.value for cell in closed_sheet[1]]
        self.assertNotIn("SLA", headers)
        self.assertEqual("CHANGE", closed_sheet.cell(2, headers.index("Category") + 1).value)
        self.assertEqual("Status Reason", headers[-2])
        self.assertEqual("Unsuccessful", closed_sheet.cell(2, len(headers) - 1).value)


if __name__ == "__main__":
    unittest.main()
