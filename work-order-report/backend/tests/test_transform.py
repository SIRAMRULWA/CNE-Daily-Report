import unittest
from datetime import datetime
from unittest.mock import patch

from pipeline.models import ChangeRecord
from pipeline.transform import transform_records


class TransformEligibilityTests(unittest.TestCase):
    @staticmethod
    def record(**overrides):
        values = {
            "request_id": "INC0001",
            "task_id": "TAS0001",
            "op_cat_tier1": "FAULTS",
            "assignee_group": "Team A",
            "summary": "Test task",
            "assignee": "Another Person",
            "priority": "Medium",
            "status": "Assigned",
            "status_reason": None,
            "create_date": None,
            "assign_time": datetime(2026, 7, 28, 8, 0),
            "closed_time": None,
            "scheduled_start": None,
            "scheduled_end": None,
            "notes": None,
        }
        values.update(overrides)
        return ChangeRecord(**values)

    def transform(self, *records):
        with patch(
            "pipeline.transform.load_group_patterns",
            return_value=[
                ("Appl:TSS Operational Support:OSS", "INTSS"),
                ("Team A", "INTSS"),
            ],
        ):
            return transform_records(
                list(records),
                as_of=datetime(2026, 7, 28, 9, 0),
            )

    def test_excludes_every_record_assigned_to_leonora_de_kock(self):
        records = self.transform(
            self.record(assignee=" Leonora De Kock "),
            self.record(
                request_id="CRQ0001",
                op_cat_tier1="CHANGE",
                assignee="LEONORA DE KOCK",
                scheduled_end=datetime(2026, 7, 28, 12, 0),
            ),
            self.record(
                request_id="WO0001",
                op_cat_tier1="SECURITY",
                assignee="leonora de kock",
            ),
        )

        self.assertTrue(all(record.is_excluded for record in records))

    def test_includes_security_work_orders(self):
        record = self.transform(
            self.record(
                request_id="WO0002",
                op_cat_tier1="SECURITY",
            )
        )[0]

        self.assertEqual("ACCESS", record.report_category)
        self.assertFalse(record.is_excluded)
        self.assertEqual("WITHIN_SLA", record.sla_status)

    def test_excludes_security_work_orders_assigned_to_tss(self):
        record = self.transform(
            self.record(
                request_id="WO0003",
                op_cat_tier1="SECURITY",
                assignee_group="Appl:TSS Operational Support:OSS",
            )
        )[0]

        self.assertEqual("ACCESS", record.report_category)
        self.assertTrue(record.is_excluded)

    def test_still_excludes_non_security_work_orders(self):
        record = self.transform(
            self.record(
                request_id="WO0004",
                op_cat_tier1="WORK ORDER",
                summary="Password access request",
                notes="ARM: security-related work",
            )
        )[0]

        self.assertTrue(record.is_excluded)


if __name__ == "__main__":
    unittest.main()
