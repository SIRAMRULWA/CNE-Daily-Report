"""Database-free tests for the data-retention allowlist."""

import unittest
from unittest.mock import MagicMock, patch

from app_core.retention import PURGE_TARGETS, enforce_retention


class RetentionTests(unittest.TestCase):
    def test_only_business_payload_tables_are_purged(self):
        tables = {target.table for target in PURGE_TARGETS}
        self.assertEqual(
            {
                "staging.raw_changes",
                "staging.elt_rejected_records",
                "reporting.daily_report_records",
                "reporting.daily_report_success_closures",
                "reporting.daily_report_closed_changes",
                "reporting.daily_report_summary",
            },
            tables,
        )
        self.assertFalse(any("activity_log" in table for table in tables))
        self.assertFalse(any("login_history" in table for table in tables))
        self.assertFalse(any("elt_run_log" in table for table in tables))

    @patch("app_core.retention.get_cursor")
    def test_cleanup_deletes_targets_and_records_audit_event(self, get_cursor):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"relation": "present"}
        cursor.rowcount = 3
        get_cursor.return_value.__enter__.return_value = cursor

        deleted = enforce_retention(days=7, timezone="Africa/Johannesburg")

        self.assertEqual(set(deleted), {target.table for target in PURGE_TARGETS})
        self.assertTrue(all(count == 3 for count in deleted.values()))
        sql = "\n".join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn("DELETE FROM staging.raw_changes", sql)
        self.assertIn("enforce_data_retention", sql)

    def test_zero_day_retention_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least 1"):
            enforce_retention(days=0)


if __name__ == "__main__":
    unittest.main()
