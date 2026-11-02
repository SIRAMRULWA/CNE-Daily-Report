"""Database-free tests for the Work Order report capability boundary."""

import unittest
from datetime import date
from unittest.mock import patch

from capabilities.daily_reports import repository
from capabilities.daily_reports.service import DailyReportService


class WorkOrderReportCapabilityTests(unittest.TestCase):
    def test_day_window_uses_selected_date(self):
        selected, start, end = repository._date_window(date(2026, 7, 13), "day")
        self.assertEqual((date(2026, 7, 13),) * 3, (selected, start, end))

    def test_week_window_is_monday_through_sunday(self):
        selected, start, end = repository._date_window(date(2026, 7, 15), "week")
        self.assertEqual(date(2026, 7, 13), start)
        self.assertEqual(date(2026, 7, 19), end)
        self.assertEqual(date(2026, 7, 15), selected)

    def test_assignee_group_filter_targets_support_group(self):
        where, params = repository._scope_filters(
            date(2026, 7, 13), date(2026, 7, 13), "INTSS", "Team A"
        )
        self.assertIn("division = %s", where)
        self.assertIn("support_group = %s", where)
        self.assertEqual([date(2026, 7, 13), date(2026, 7, 13), "INTSS", "Team A"], params)

    @patch("capabilities.daily_reports.repository.run_query", return_value=[])
    def test_open_sla_filter_reads_only_open_snapshot(self, run_query):
        repository._report_records(date(2026, 7, 13), date(2026, 7, 13), sla="BREACHED")
        sql = run_query.call_args.args[0]
        self.assertEqual(1, run_query.call_count)
        self.assertIn("reporting.wo_report_records", sql)

    @patch("capabilities.daily_reports.repository.run_query", return_value=[])
    def test_completed_sla_filter_reads_only_completed_snapshot(self, run_query):
        repository._report_records(date(2026, 7, 13), date(2026, 7, 13), sla="MISSED_TARGET")
        self.assertEqual(1, run_query.call_count)
        self.assertIn("reporting.wo_completed", run_query.call_args.args[0])

    @patch("capabilities.daily_reports.repository.run_query", return_value=[])
    def test_no_sla_filter_reads_open_and_completed(self, run_query):
        result = repository._report_records(date(2026, 7, 13), date(2026, 7, 13))
        tables = " ".join(call.args[0] for call in run_query.call_args_list)
        self.assertIn("reporting.wo_report_records", tables)
        self.assertIn("reporting.wo_completed", tables)
        self.assertEqual(0, result["count"])

    @patch("capabilities.daily_reports.service.repository.daily_report_view")
    def test_service_delegates_complete_view_contract(self, report_view):
        report_view.return_value = {"data_available": False, "summary": {"rows": []}}
        result = DailyReportService().report_view(
            report_date=date(2026, 7, 13), division="INTSS", include_records=True,
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


if __name__ == "__main__":
    unittest.main()
