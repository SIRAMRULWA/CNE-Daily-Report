"""Read-only custom Helix Work Order report tests."""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.routers.helix_raw_reports import (
    RawReportRequest,
    _resolve_statuses,
    create_raw_report,
    raw_report_fields,
)
from helix.extractor import HelixExtractor
from helix.query import HelixQueryBuilder


class HelixRawReportTests(unittest.TestCase):
    def test_omitted_statuses_include_every_status(self):
        payload = RawReportRequest(start="2026-07-01T00:00:00", end="2026-07-02T00:00:00")
        self.assertIsNone(_resolve_statuses(payload))

    def test_include_closed_adds_completed_statuses(self):
        payload = RawReportRequest(
            start="2026-07-01T00:00:00",
            end="2026-07-02T00:00:00",
            statuses=["Assigned"],
            include_closed=True,
        )
        statuses = _resolve_statuses(payload)
        self.assertIn("Assigned", statuses)
        self.assertIn("Completed", statuses)
        self.assertIn("Closed", statuses)

    def test_request_needs_a_range_or_work_order_ids(self):
        with self.assertRaises(ValueError):
            RawReportRequest()
        RawReportRequest(work_order_ids=["WO1"])

    def test_fields_endpoint_describes_the_work_order_form(self):
        fields = raw_report_fields()
        self.assertEqual("WOI:WorkOrder", fields["form"])
        names = {field["name"] for field in fields["fields"]}
        self.assertTrue({"work_order_id", "target_date", "requester"}.issubset(names))
        self.assertIn("days_to_target", fields["derived_sla_fields"])

    def test_query_filters_by_exact_assignee(self):
        query = HelixQueryBuilder().raw_report(
            start_date="2026-07-01",
            end_date="2026-07-02",
            assignees=["Jane Doe", 'A "Quoted" Owner'],
        )
        self.assertIn("'Request Assignee' = \"Jane Doe\"", query)
        self.assertIn("'Request Assignee' = \"A \\\"Quoted\\\" Owner\"", query)

    @patch("pipeline.transform.load_group_patterns", return_value=[])
    def test_calculate_sla_adds_shared_derived_fields(self, _groups):
        extractor = HelixExtractor()
        target = datetime.now() + timedelta(hours=10)
        extractor._fetch_page = MagicMock(return_value=[{
            "values": {
                "Work Order ID": "WO0001",
                "Work Order Type": "General",
                "Request Assignee": "Jane Doe",
                "Support Group Name": "Team A",
                "Status": "Assigned",
                "Submit Date": datetime.now() - timedelta(hours=5),
                "Scheduled End Date": target,
            },
        }])

        rows = extractor.extract_raw_report(
            start_date="2026-07-01",
            end_date="2026-07-30",
            fields=["work_order_id", "assignee"],
            assignees=["Jane Doe"],
            calculate_sla=True,
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("WO0001", rows[0]["work_order_id"])
        self.assertEqual("General", rows[0]["report_category"])
        self.assertEqual("NEARING_SLA", rows[0]["sla_status"])
        self.assertAlmostEqual(5.0, rows[0]["hours_open"], places=1)
        self.assertEqual(0, rows[0]["days_to_target"])
        qualification = extractor._fetch_page.call_args.args[1]
        self.assertIn("'Request Assignee' = \"Jane Doe\"", qualification)

    @patch("api.routers.helix_raw_reports.audit_event")
    @patch("api.routers.helix_raw_reports.HelixExtractor")
    def test_endpoint_forwards_filters_and_audits(self, extractor_type, audit_event):
        extractor = extractor_type.return_value
        extractor.is_configured.return_value = True
        extractor.extract_raw_report.return_value = []
        payload = RawReportRequest(
            start="2026-07-01T00:00:00",
            end="2026-07-02T00:00:00",
            assignees=["Jane Doe"],
            work_order_ids=["WO1"],
            calculate_sla=True,
        )
        request = MagicMock()
        request.state = SimpleNamespace(current_user=SimpleNamespace(email="reader@example.com"))

        response = create_raw_report(payload, request)

        self.assertEqual("helix:WOI:WorkOrder", response["source"])
        self.assertEqual(["WO1"], response["work_order_ids"])
        kwargs = extractor.extract_raw_report.call_args.kwargs
        self.assertEqual(["Jane Doe"], kwargs["assignees"])
        self.assertEqual(["WO1"], kwargs["work_order_ids"])
        self.assertTrue(kwargs["calculate_sla"])
        self.assertEqual("reader@example.com", audit_event.call_args.kwargs["actor"])


if __name__ == "__main__":
    unittest.main()
