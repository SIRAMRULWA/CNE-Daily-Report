"""Unit tests for the Work Order Helix integration components."""

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from helix.config import HELIX_FIELD_MAP, HELIX_FORM
from helix.datetime_utils import format_helix_timestamp
from helix.extractor import HelixExtractor
from helix.mapper import HelixWorkOrderMapper
from helix.query import HelixQueryBuilder

TZ = ZoneInfo("Africa/Johannesburg")


class HelixComponentTests(unittest.TestCase):
    def test_default_form_is_work_order(self):
        self.assertEqual("WOI:WorkOrder", HELIX_FORM)
        self.assertEqual("work_order_id", HELIX_FIELD_MAP["Work Order ID"])

    def test_open_query_filters_support_group_and_status(self):
        query = HelixQueryBuilder().work_order_query(
            groups=["Team A", 'Team "B"'],
            statuses=["Assigned", "Pending"],
            start_date="2026-07-01",
            end_date="2026-07-02",
        )
        self.assertIn("'Support Group Name' = \"Team A\"", query)
        self.assertIn("'Support Group Name' = \"Team \\\"B\\\"\"", query)
        self.assertIn("'Status' = \"Assigned\"", query)
        self.assertIn("'Submit Date' >=", query)
        self.assertIn("'Submit Date' <=", query)

    def test_completion_window_is_previous_0700_to_0700(self):
        start, end = HelixQueryBuilder.completion_window(datetime(2026, 11, 2, 7, 15, tzinfo=TZ))
        self.assertEqual(datetime(2026, 11, 1, 7, 0, tzinfo=TZ), start)
        self.assertEqual(datetime(2026, 11, 2, 7, 0, tzinfo=TZ), end)

    def test_completion_window_before_0700_uses_the_day_before(self):
        start, end = HelixQueryBuilder.completion_window(datetime(2026, 11, 2, 6, 0, tzinfo=TZ))
        self.assertEqual(datetime(2026, 10, 31, 7, 0, tzinfo=TZ), start)
        self.assertEqual(datetime(2026, 11, 1, 7, 0, tzinfo=TZ), end)

    def test_completion_query_filters_completed_statuses_and_dates(self):
        query, _, _ = HelixQueryBuilder().completions(
            ["Team A"], now=datetime(2026, 11, 2, 7, 15, tzinfo=TZ)
        )
        self.assertIn("'Status' = \"Completed\"", query)
        self.assertIn("'Completed Date' >=", query)
        self.assertIn("'Completed Date' <", query)

    def test_timestamp_formatter_treats_naive_dates_as_workspace_local(self):
        expected = int(datetime(2026, 7, 23, 10, 32, tzinfo=TZ).timestamp())
        self.assertEqual(str(expected), format_helix_timestamp("2026-07-23 10:32"))

    def test_mapper_builds_work_order_record(self):
        submitted = datetime(2026, 7, 23, 8, 32, tzinfo=UTC)
        record = HelixWorkOrderMapper.record({
            "values": {
                "Work Order ID": " WO0000000000123 ",
                "Summary": " Install router ",
                "Work Order Type": "General",
                "Status": "Assigned",
                "Customer First Name": "Thandi",
                "Customer Last Name": "Nkosi",
                "Support Group Name": "Team A",
                "Request Assignee": "Jane Doe",
                "Submit Date": int(submitted.timestamp()),
                "Scheduled End Date": "2026-07-30",
            }
        })
        self.assertEqual("WO0000000000123", record.work_order_id)
        self.assertEqual("Install router", record.summary)
        self.assertEqual("General", record.work_order_type)
        self.assertEqual("Thandi Nkosi", record.requester)
        self.assertEqual("Team A", record.support_group)
        self.assertEqual("Jane Doe", record.assignee)
        self.assertEqual(10, record.submit_date.hour)
        self.assertEqual(datetime(2026, 7, 30, 23, 59, 59), record.target_date)
        self.assertEqual("helix_api", record.source)

    def test_mapper_skips_entries_without_an_id(self):
        self.assertIsNone(HelixWorkOrderMapper.record({"values": {"Summary": "x"}}))

    def test_extractor_reads_the_work_order_form(self):
        extractor = HelixExtractor()
        extractor._client.fetch_page = MagicMock(return_value=[{"values": {}}])
        self.assertEqual([{"values": {}}], extractor._fetch_page(20, "q"))
        extractor._client.fetch_page.assert_called_once_with(20, "q")

    @patch("helix.extractor.HelixExtractor.is_configured", return_value=True)
    def test_extractor_yields_open_then_completed_without_duplicates(self, _configured):
        extractor = HelixExtractor()
        pages = {
            "open": [{"values": {"Work Order ID": "WO1", "Status": "Assigned"}},
                     {"values": {"Work Order ID": "WO2", "Status": "Pending"}}],
            "done": [{"values": {"Work Order ID": "WO2", "Status": "Completed"}},
                     {"values": {"Work Order ID": "WO3", "Status": "Completed"}}],
        }
        extractor._fetch_page = MagicMock(
            side_effect=lambda offset, query: (
                [] if offset else pages["done" if "Completed Date" in query else "open"]
            )
        )
        batches = list(extractor.extract_work_orders(support_groups=["Team A"]))
        ids = [record.work_order_id for batch in batches for record in batch]
        self.assertEqual(["WO1", "WO2", "WO3"], ids)


if __name__ == "__main__":
    unittest.main()
