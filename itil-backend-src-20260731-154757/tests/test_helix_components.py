"""Unit tests for the split Helix integration components."""

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from helix.datetime_utils import format_helix_timestamp
from helix.extractor import HELIX_FIELD_MAP, HelixExtractor
from helix.mapper import HelixTaskMapper
from helix.query import HelixQueryBuilder


class HelixComponentTests(unittest.TestCase):
    def test_query_builder_preserves_ar_qualification_shape(self):
        query = HelixQueryBuilder().task_query(
            groups=["Team A", 'Team "B"'],
            statuses=["Assigned", "Pending"],
            start_date="2026-07-01",
            end_date="2026-07-02",
        )
        self.assertIn("'Assignee Group' = \"Team A\"", query)
        self.assertIn("'Assignee Group' = \"Team \\\"B\\\"\"", query)
        self.assertIn("'Status' = \"Assigned\"", query)
        self.assertIn("'Create Date' >=", query)
        self.assertIn("'Create Date' <=", query)
        self.assertNotIn(" IN (", query)

    def test_timestamp_formatter_treats_naive_dates_as_workspace_local(self):
        expected = int(
            datetime(2026, 7, 23, 10, 32)
            .replace(tzinfo=ZoneInfo("Africa/Johannesburg"))
            .timestamp()
        )
        self.assertEqual(str(expected), format_helix_timestamp("2026-07-23 10:32"))

    def test_mapper_preserves_canonical_record_contract(self):
        assigned = datetime(2026, 7, 23, 8, 32, tzinfo=UTC)
        record = HelixTaskMapper.record({
            "values": {
                "RootRequestID": " INC100 ",
                "Task ID": " TAS100 ",
                "Service Cat Tier 1": " Faults ",
                "Assignee Group": "Team A",
                "Status": "Assigned",
                "Assign Time": int(assigned.timestamp()),
                "Summary": "Test",
            }
        })
        self.assertEqual("INC100", record.request_id)
        self.assertEqual("TAS100", record.task_id)
        self.assertEqual("Faults", record.op_cat_tier1)
        self.assertEqual("helix_api", record.source)
        self.assertEqual(10, record.assign_time.hour)

    def test_facade_reexports_field_contract_and_delegates_http(self):
        self.assertEqual("request_id", HELIX_FIELD_MAP["RootRequestID"])
        extractor = HelixExtractor()
        extractor._client.fetch_task_page = MagicMock(return_value=[{"values": {}}])
        rows = extractor._fetch_page(20, "'Status' = \"Assigned\"")
        self.assertEqual([{"values": {}}], rows)
        extractor._client.fetch_task_page.assert_called_once_with(
            20, "'Status' = \"Assigned\""
        )

    def test_facade_query_method_delegates_without_changing_signature(self):
        extractor = HelixExtractor()
        query = extractor._build_query(
            assignee_groups=["Team A"],
            statuses=["Assigned"],
        )
        self.assertEqual(
            "('Assignee Group' = \"Team A\") AND ('Status' = \"Assigned\")",
            query,
        )


if __name__ == "__main__":
    unittest.main()
