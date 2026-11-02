"""Regression tests for report-email schedule eligibility."""

import unittest
from datetime import UTC, datetime, time

from notifications.sender import _is_due


class ReportEmailSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.subscription = {
            "timezone": "Africa/Johannesburg",
            "send_time": time(13, 0),
            "frequency": "DAILY",
            "weekday": None,
        }

    def test_report_is_due_in_current_polling_window(self):
        due, report_date = _is_due(
            self.subscription, datetime(2026, 7, 22, 11, 1, tzinfo=UTC)
        )
        self.assertTrue(due)
        self.assertEqual(datetime(2026, 7, 22).date(), report_date)

    def test_report_does_not_backfill_later_in_the_day(self):
        due, _ = _is_due(
            self.subscription, datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
        )
        self.assertFalse(due)

    def test_new_or_updated_report_does_not_run_for_past_occurrence(self):
        self.subscription["updated_at"] = datetime(
            2026, 7, 22, 11, 0, 30, tzinfo=UTC
        )
        due, _ = _is_due(
            self.subscription, datetime(2026, 7, 22, 11, 1, tzinfo=UTC)
        )
        self.assertFalse(due)


if __name__ == "__main__":
    unittest.main()
