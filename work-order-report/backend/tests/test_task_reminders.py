"""Offline tests for task reminder classification and rendering."""

import unittest
from unittest.mock import MagicMock, patch
from datetime import UTC, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from capabilities.task_reminders.service import TaskReminderService
from helix.extractor import HelixExtractor
from notifications.task_reminder_sender import _scheduled_occurrence
from notifications.task_reminders import _daily_report_rows, _excel, _html, _live_summary, _prepare, execute
from pipeline.models import ChangeRecord


class TaskReminderTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
        self.rows = [
            {
                "request_id": "INC0001",
                "task_id": "TAS0001",
                "priority": "High",
                "status": "Assigned",
                "report_category": "INCIDENT",
                "sla_status": "BREACHED",
                "assignee_group": "Team A",
                "assignee": "",
                "create_date": self.now - timedelta(days=10),
                "hours_open": "240.126",
                "summary": "Old high-priority task",
            },
            {
                "request_id": "INC0002",
                "task_id": "TAS0002",
                "priority": "Medium",
                "status": "Work In Progress",
                "report_category": "CHANGE",
                "sla_status": "NEARING_SLA",
                "assignee_group": "Team B",
                "assignee": "Owner",
                "create_date": self.now - timedelta(days=1),
                "summary": "Normal open task",
            },
        ]

    def test_prepare_highlights_attention_and_preserves_all_rows(self):
        prepared = _prepare(self.rows, self.now)
        self.assertEqual(2, len(prepared))
        self.assertTrue(prepared[0]["requires_attention"])
        self.assertIn("High priority", prepared[0]["attention"])
        self.assertIn("Unassigned", prepared[0]["attention"])
        self.assertEqual(10, prepared[0]["age_days"])
        self.assertTrue(prepared[1]["requires_attention"])

    def test_excel_contains_complete_open_task_list(self):
        prepared = _prepare(self.rows, self.now)
        attachment = _excel(prepared, "INTSS", self.now)
        workbook = load_workbook(BytesIO(attachment.content))
        self.assertEqual(["Team A", "Team B"], workbook.sheetnames)
        sheet = workbook["Team A"]
        self.assertEqual(2, sheet.max_row)
        self.assertEqual("SLA", sheet.cell(1, 1).value)
        self.assertEqual("INC0001", sheet.cell(2, 2).value)
        self.assertEqual(240.13, sheet.cell(2, 9).value)
        self.assertEqual("0.00", sheet.cell(2, 9).number_format)
        self.assertEqual("A2", sheet.freeze_panes)
        self.assertEqual("00E60000", sheet.cell(1, 1).fill.fgColor.rgb)
        self.assertEqual("daily-report-intss-2026-07-22.xlsx", attachment.filename)

    def test_html_contains_summary_and_call_to_action(self):
        prepared = _prepare(self.rows, self.now)
        body = _html({"division": "INTSS", "assignee_group": None}, prepared, self.now)
        self.assertIn("INTSS Tasks Reminder", body)
        self.assertIn("By Group", body)
        self.assertIn("Open Tasks", body)
        self.assertIn("Near SLA", body)
        self.assertIn("Breached", body)
        self.assertIn("Daily Report format", body)
        self.assertIn('src="cid:vodacom-logo"', body)
        self.assertIn("Oldest (Days)", body)
        self.assertIn(">10</div>", body)
        self.assertIn("background:#EDF7ED", body)
        self.assertIn("background:#FFF0F0", body)
        self.assertIn("background:#FFF8E6", body)
        self.assertIn("background:#EEF4FF", body)
        self.assertIn("SAST", body)
        self.assertNotIn("UTC", body)
        self.assertNotIn("Closed Successfully Yesterday", body)

    def test_helix_epoch_is_converted_to_workspace_time(self):
        extractor = HelixExtractor()
        assigned_utc = datetime(2026, 7, 22, 9, 17, 54, tzinfo=UTC)
        record = extractor._entry_to_record({
            "values": {
                "RootRequestID": "INC100",
                "Task ID": "TAS100",
                "Assignee Group": "Team A",
                "Status": "Assigned",
                "Summary": "Timezone check",
                "Assign Time": int(assigned_utc.timestamp()),
            }
        })

        self.assertIsNotNone(record)
        expected = assigned_utc.astimezone(
            ZoneInfo("Africa/Johannesburg")
        ).replace(tzinfo=None)
        self.assertEqual(expected, record.assign_time)

    def test_live_summary_matches_daily_report_bands_and_categories(self):
        summary = _live_summary(_prepare(self.rows, self.now))
        by_band = {row["sla_band"]: row for row in summary if row["assignee_group"] == "Team A"}
        self.assertEqual(1, by_band["Total Open Calls"]["incident_count"])
        self.assertEqual(1, by_band["Breached Calls"]["total_count"])

    @patch("capabilities.task_reminders.service.audit_event")
    @patch("capabilities.task_reminders.service.configured_transport")
    @patch("capabilities.task_reminders.service.HelixExtractor")
    @patch("capabilities.task_reminders.service.get_organization_service")
    @patch("notifications.task_reminders._daily_report_rows")
    def test_execute_queries_live_helix_and_records_sent_execution(
        self, daily_rows, organization_factory, extractor_class,
        configured_transport, audit_event
    ):
        subscription = {
            "id": 12,
            "name": "INTSS reminder",
            "division": "INTSS",
            "assignee_group": None,
            "recipients": ["ops@example.com"],
            "cc_recipients": [],
            "subject": None,
            "max_records": 100,
            "enabled": True,
        }
        repository = MagicMock()
        repository.get_subscription.return_value = subscription
        repository.claim_execution.return_value = (
            {"id": 99, "subscription_id": 12, "status": "RUNNING"},
            False,
        )
        repository.complete_execution.return_value = {
            "id": 99, "subscription_id": 12, "status": "SENT", "record_count": 2
        }
        organization_factory.return_value.list_groups.return_value = [
            {"assignee_group": "Team A"}, {"assignee_group": "Team B"}
        ]
        extractor = extractor_class.return_value
        extractor.is_configured.return_value = True
        extracted_records = [
            ChangeRecord(
                request_id="INC0001", task_id="TAS0001", op_cat_tier1="Faults",
                assignee_group="Team A", summary="Fault", assignee=None, priority="High",
                status="Assigned", status_reason=None, create_date=None, assign_time=None,
                closed_time=None, scheduled_start=None, scheduled_end=None, notes=None,
            )
        ]
        extractor.extract_changes.return_value = [extracted_records]
        daily_rows.return_value = self.rows
        transport = configured_transport.return_value
        transport.provider = "smtp"
        transport.send.return_value = "message-1"

        service = TaskReminderService(repository)
        result = service.execute(
            12, "schedule-20260722-1200", "AUTOMATION", "automation-platform"
        )

        self.assertEqual("SENT", result["status"])
        extractor.extract_changes.assert_called_once()
        call = extractor.extract_changes.call_args.kwargs
        self.assertEqual(["Team A", "Team B"], call["assignee_groups"])
        self.assertGreater(len(call["statuses"]), 0)
        self.assertEqual(101, call["max_records"])
        self.assertFalse(call["include_successful_closures"])
        transport.send.assert_called_once()
        repository.complete_execution.assert_called_once()
        audit_event.assert_called_once()

    @patch("pipeline.transform.load_group_patterns", return_value=[("Team A", "INTSS")])
    def test_live_rows_use_daily_report_exclusions(self, _patterns):
        records = [
            ChangeRecord(
                request_id=request_id, task_id=task_id, op_cat_tier1=None,
                assignee_group="Team A", summary=summary, assignee=None, priority=None,
                status="Assigned", status_reason=None, create_date=None,
                assign_time=self.now.replace(tzinfo=None) - timedelta(hours=2),
                closed_time=None, scheduled_start=None, scheduled_end=None, notes=None,
            )
            for request_id, task_id, summary in (
                ("INC1", "T1", "Fault"),
                ("WO1", "T2", "Work order"),
                ("PBI1", "T3", "PBI"),
            )
        ]
        rows = _daily_report_rows(records, "INTSS", None, self.now)
        self.assertEqual(["INC1"], [row["request_id"] for row in rows])
        self.assertEqual("INCIDENT", rows[0]["report_category"])

    @patch("pipeline.transform.load_group_patterns", return_value=[("Team A", "INTSS")])
    def test_missing_sla_inputs_use_category_specific_statuses(self, _patterns):
        records = [
            ChangeRecord(
                request_id="INC1", task_id="T1", op_cat_tier1="Faults",
                assignee_group="Team A", summary="Incident", assignee=None, priority=None,
                status="Assigned", status_reason=None, create_date=None, assign_time=None,
                closed_time=None, scheduled_start=None, scheduled_end=None, notes=None,
            ),
            ChangeRecord(
                request_id="CRQ1", task_id="T2", op_cat_tier1="Change",
                assignee_group="Team A", summary="Change", assignee=None, priority=None,
                status="Assigned", status_reason=None, create_date=None, assign_time=None,
                closed_time=None, scheduled_start=None, scheduled_end=None, notes=None,
            ),
        ]
        rows = _daily_report_rows(records, "INTSS", None, self.now)
        by_request = {row["request_id"]: row["sla_status"] for row in rows}
        self.assertEqual("NO_ASSIGN_TIME", by_request["INC1"])
        self.assertEqual("NO_SCHEDULE", by_request["CRQ1"])

    def test_admin_schedule_time_drives_due_slot(self):
        subscription = {
            "timezone": "Africa/Johannesburg", "send_time": datetime.strptime("13:00", "%H:%M").time(),
            "frequency": "DAILY", "weekday": None,
        }
        before = datetime(2026, 7, 22, 10, 59, tzinfo=UTC)
        after = datetime(2026, 7, 22, 11, 1, tzinfo=UTC)
        self.assertFalse(_scheduled_occurrence(subscription, before)[0])
        due, key = _scheduled_occurrence(subscription, after)
        self.assertTrue(due)
        self.assertEqual("scheduled-2026-07-22-1300", key)

    def test_schedule_does_not_backfill_after_polling_window(self):
        subscription = {
            "timezone": "Africa/Johannesburg",
            "send_time": datetime.strptime("13:00", "%H:%M").time(),
            "frequency": "DAILY",
            "weekday": None,
        }
        much_later = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
        self.assertFalse(_scheduled_occurrence(subscription, much_later)[0])

    def test_new_or_updated_schedule_does_not_run_for_past_occurrence(self):
        subscription = {
            "timezone": "Africa/Johannesburg",
            "send_time": datetime.strptime("13:00", "%H:%M").time(),
            "frequency": "DAILY",
            "weekday": None,
            # Configuration was saved at 13:00:30 local, after today's slot.
            "updated_at": datetime(2026, 7, 22, 11, 0, 30, tzinfo=UTC),
        }
        first_poll = datetime(2026, 7, 22, 11, 1, tzinfo=UTC)
        self.assertFalse(_scheduled_occurrence(subscription, first_poll)[0])

    def test_shared_extractor_supports_read_only_reminder_scope(self):
        extractor = HelixExtractor()
        extractor.is_configured = MagicMock(return_value=True)
        extractor._fetch_page = MagicMock(return_value=[{
            "values": {
                "RootRequestID": "INC100",
                "Task ID": "TAS100",
                "Assignee Group": "Team A",
                "Status": "Assigned",
                "Summary": "Live task",
            }
        }])
        extractor._enrich_change_schedules = MagicMock()

        batches = list(extractor.extract_changes(
            assignee_groups=["Team A"],
            statuses=["Assigned"],
            max_records=2,
            include_successful_closures=False,
        ))

        self.assertEqual("INC100", batches[0][0].request_id)
        query = extractor._fetch_page.call_args.args[1]
        self.assertIn("'Assignee Group' = \"Team A\"", query)
        self.assertIn("'Status' = \"Assigned\"", query)
        extractor._enrich_change_schedules.assert_called_once_with(batches[0])


if __name__ == "__main__":
    unittest.main()
