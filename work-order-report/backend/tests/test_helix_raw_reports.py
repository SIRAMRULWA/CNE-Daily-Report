"""Read-only Helix report filters and SLA calculation regression tests."""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.routers.helix_raw_reports import (
    RawReportRequest,
    _resolve_statuses,
    create_raw_report,
)
from helix.extractor import HelixExtractor
from helix.query import HelixQueryBuilder


class HelixRawReportTests(unittest.TestCase):
    def test_omitted_statuses_include_every_status(self):
        payload = RawReportRequest(
            start="2026-07-01T00:00:00",
            end="2026-07-02T00:00:00",
        )

        self.assertIsNone(_resolve_statuses(payload))

    def test_include_closed_adds_closed_statuses_to_open_filter(self):
        payload = RawReportRequest(
            start="2026-07-01T00:00:00",
            end="2026-07-02T00:00:00",
            statuses=["Assigned"],
            include_closed=True,
        )

        statuses = _resolve_statuses(payload)
        self.assertIn("Assigned", statuses)
        self.assertIn("Closed", statuses)
        self.assertIn("Cancelled", statuses)

    def test_query_filters_tasks_by_exact_assignee(self):
        query = HelixQueryBuilder().raw_report(
            start_date="2026-07-01",
            end_date="2026-07-02",
            assignees=["Jane Doe", 'A "Quoted" Owner'],
        )

        self.assertIn("'Assignee' = \"Jane Doe\"", query)
        self.assertIn("'Assignee' = \"A \\\"Quoted\\\" Owner\"", query)

    @patch("pipeline.transform.load_group_patterns", return_value=[])
    def test_calculate_sla_adds_shared_derived_fields(self, _groups):
        extractor = HelixExtractor()
        assigned = datetime.now() - timedelta(hours=23)
        extractor._fetch_page = MagicMock(return_value=[{
            "values": {
                "RootRequestID": "INC0001",
                "Task ID": "TAS0001",
                "Service Cat Tier 1": "FAULTS",
                "Assignee": "Jane Doe",
                "Assignee Group": "Team A",
                "Status": "Assigned",
                "Assign Time": assigned,
            },
        }])

        rows = extractor.extract_raw_report(
            start_date="2026-07-01",
            end_date="2026-07-30",
            fields=["request_id", "assignee"],
            assignees=["Jane Doe"],
            calculate_sla=True,
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("INC0001", rows[0]["request_id"])
        self.assertEqual("Jane Doe", rows[0]["assignee"])
        self.assertEqual("INCIDENT", rows[0]["report_category"])
        self.assertEqual("NEARING_SLA", rows[0]["sla_status"])
        self.assertAlmostEqual(23.0, rows[0]["hours_open"], places=1)
        self.assertIn("sla_calculated_at", rows[0])
        qualification = extractor._fetch_page.call_args.args[1]
        self.assertIn("'Assignee' = \"Jane Doe\"", qualification)

    @patch("api.routers.helix_raw_reports.audit_event")
    @patch("api.routers.helix_raw_reports.HelixExtractor")
    def test_endpoint_forwards_assignee_and_sla_options(
        self, extractor_type, audit_event
    ):
        extractor = extractor_type.return_value
        extractor.is_configured.return_value = True
        extractor.extract_raw_report.return_value = []
        payload = RawReportRequest(
            start="2026-07-01T00:00:00",
            end="2026-07-02T00:00:00",
            assignees=["Jane Doe"],
            calculate_sla=True,
        )

        request = MagicMock()
        request.state = SimpleNamespace(
            current_user=SimpleNamespace(email="reader@example.com")
        )
        response = create_raw_report(payload, request)

        self.assertEqual(["Jane Doe"], response["assignees"])
        self.assertTrue(response["calculate_sla"])
        kwargs = extractor.extract_raw_report.call_args.kwargs
        self.assertEqual(["Jane Doe"], kwargs["assignees"])
        self.assertTrue(kwargs["calculate_sla"])
        audit_event.assert_called_once()
        self.assertEqual(
            "reader@example.com",
            audit_event.call_args.kwargs["actor"],
        )


if __name__ == "__main__":
    unittest.main()
