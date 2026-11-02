"""Work Order transform and SLA rule tests (design document: Transformation and SLA rules)."""

import unittest
from datetime import date, datetime, timedelta

from helix.datetime_utils import parse_target_date
from pipeline.models import WorkOrderRecord
from pipeline.transform import (
    UNKNOWN_DIVISION,
    classify_category,
    classify_division,
    days_to_target,
    hours_open,
    is_report_eligible,
    sla_status,
    transform_records,
)

NOW = datetime(2026, 11, 2, 10, 0, 0)
PATTERNS = [("Appl:IN TELECOMS:OSS", "INTSS"), ("TRANSPORT:CDN", "CDN"),
            ("TRANSPORT:CDN NORTH", "CDN-NORTH")]


def work_order(**overrides) -> WorkOrderRecord:
    values = {
        "work_order_id": "WO0000000000001",
        "status": "Assigned",
        "support_group": "Appl:IN TELECOMS:OSS",
        "submit_date": NOW - timedelta(days=3),
        "target_date": NOW + timedelta(days=5),
    }
    values.update(overrides)
    return WorkOrderRecord(**values)


class OpenSlaStatusTests(unittest.TestCase):
    def test_target_more_than_24_hours_away_is_within_sla(self):
        rec = work_order(target_date=NOW + timedelta(hours=24, seconds=1))
        self.assertEqual("WITHIN_SLA", sla_status(rec, NOW))

    def test_exactly_24_hours_before_target_is_still_within_sla(self):
        rec = work_order(target_date=NOW + timedelta(hours=24))
        self.assertEqual("WITHIN_SLA", sla_status(rec, NOW))

    def test_inside_the_24_hour_window_is_nearing(self):
        rec = work_order(target_date=NOW + timedelta(hours=23, minutes=59))
        self.assertEqual("NEARING_SLA", sla_status(rec, NOW))

    def test_at_the_target_moment_is_nearing_not_breached(self):
        rec = work_order(target_date=NOW)
        self.assertEqual("NEARING_SLA", sla_status(rec, NOW))

    def test_one_second_past_target_is_breached_with_no_grace(self):
        rec = work_order(target_date=NOW - timedelta(seconds=1))
        self.assertEqual("BREACHED", sla_status(rec, NOW))

    def test_missing_target_date_is_no_target_date(self):
        rec = work_order(target_date=None)
        self.assertEqual("NO_TARGET_DATE", sla_status(rec, NOW))

    def test_every_open_status_is_measured(self):
        for status in ("Assigned", "Pending", "Waiting Approval", "Planning", "In Progress"):
            with self.subTest(status=status):
                rec = work_order(status=status, target_date=NOW - timedelta(days=1))
                self.assertEqual("BREACHED", sla_status(rec, NOW))


class DateOnlyTargetTests(unittest.TestCase):
    def test_date_only_string_is_due_at_end_of_that_day(self):
        self.assertEqual(datetime(2026, 11, 2, 23, 59, 59), parse_target_date("2026-11-02"))

    def test_date_object_is_due_at_end_of_that_day(self):
        self.assertEqual(datetime(2026, 11, 2, 23, 59, 59), parse_target_date(date(2026, 11, 2)))

    def test_date_with_time_keeps_its_time(self):
        self.assertEqual(datetime(2026, 11, 2, 9, 30), parse_target_date("2026-11-02 09:30:00"))

    def test_epoch_seconds_are_not_treated_as_date_only(self):
        parsed = parse_target_date("1793606400")
        self.assertNotEqual((23, 59, 59), (parsed.hour, parsed.minute, parsed.second))

    def test_date_only_target_is_not_breached_during_its_own_day(self):
        rec = work_order(target_date=parse_target_date("2026-11-02"))
        self.assertEqual("NEARING_SLA", sla_status(rec, datetime(2026, 11, 2, 23, 59, 59)))
        self.assertEqual("BREACHED", sla_status(rec, datetime(2026, 11, 3, 0, 0, 0)))


class CompletedSlaStatusTests(unittest.TestCase):
    def test_completed_on_or_before_target_met_target(self):
        target = NOW - timedelta(hours=2)
        rec = work_order(status="Completed", target_date=target, completed_date=target)
        self.assertEqual("MET_TARGET", sla_status(rec, NOW))

    def test_completed_after_target_missed_target(self):
        target = NOW - timedelta(hours=2)
        rec = work_order(status="Closed", target_date=target,
                         completed_date=target + timedelta(seconds=1))
        self.assertEqual("MISSED_TARGET", sla_status(rec, NOW))

    def test_completed_without_target_is_no_target_date(self):
        rec = work_order(status="Completed", target_date=None, completed_date=NOW)
        self.assertEqual("NO_TARGET_DATE", sla_status(rec, NOW))

    def test_excluded_statuses_are_out_of_scope(self):
        for status in ("Cancelled", "Rejected", "Draft", "Something new"):
            with self.subTest(status=status):
                self.assertEqual("OUT_OF_SCOPE", sla_status(work_order(status=status), NOW))


class DerivedValueTests(unittest.TestCase):
    def test_hours_open_counts_from_submit_date_to_now(self):
        rec = work_order(submit_date=NOW - timedelta(hours=30))
        self.assertAlmostEqual(30.0, hours_open(rec, NOW))

    def test_hours_open_stops_at_completed_date(self):
        rec = work_order(status="Completed", submit_date=NOW - timedelta(hours=30),
                         completed_date=NOW - timedelta(hours=10))
        self.assertAlmostEqual(20.0, hours_open(rec, NOW))

    def test_hours_open_is_none_without_submit_date(self):
        self.assertIsNone(hours_open(work_order(submit_date=None), NOW))

    def test_days_to_target_counts_whole_days_remaining(self):
        rec = work_order(target_date=NOW + timedelta(days=2, hours=5))
        self.assertEqual(2, days_to_target(rec, NOW))

    def test_days_to_target_is_negative_when_overdue(self):
        rec = work_order(target_date=NOW - timedelta(hours=1))
        self.assertEqual(-1, days_to_target(rec, NOW))
        rec = work_order(target_date=NOW - timedelta(days=3, hours=1))
        self.assertEqual(-4, days_to_target(rec, NOW))

    def test_category_prefers_type_then_tier1_then_unclassified(self):
        self.assertEqual("Service Request", classify_category(
            work_order(work_order_type="Service Request", category_tier1="Access")))
        self.assertEqual("Access", classify_category(work_order(category_tier1=" Access ")))
        self.assertEqual("Unclassified", classify_category(work_order()))


class DivisionAndEligibilityTests(unittest.TestCase):
    def test_support_group_maps_to_division(self):
        self.assertEqual("INTSS", classify_division("Appl:IN TELECOMS:OSS", PATTERNS))

    def test_longest_pattern_wins(self):
        self.assertEqual("CDN-NORTH", classify_division("TRANSPORT:CDN NORTH", PATTERNS))

    def test_unmapped_group_is_unknown_and_excluded(self):
        self.assertEqual(UNKNOWN_DIVISION, classify_division("Someone Else", PATTERNS))
        rec = work_order(support_group="Someone Else")
        transform_records([rec], as_of=NOW, group_patterns=PATTERNS)
        self.assertTrue(rec.is_excluded)

    def test_open_and_completed_in_scope_others_excluded(self):
        self.assertTrue(is_report_eligible(work_order(division="INTSS")))
        self.assertTrue(is_report_eligible(work_order(division="INTSS", status="Completed")))
        self.assertFalse(is_report_eligible(work_order(division="INTSS", status="Cancelled")))
        self.assertFalse(is_report_eligible(work_order(division=None)))


class TransformRecordsTests(unittest.TestCase):
    def test_transform_sets_every_derived_field(self):
        rec = work_order(target_date=NOW - timedelta(hours=5), work_order_type="Standard")
        transform_records([rec], as_of=NOW, group_patterns=PATTERNS)
        self.assertEqual("INTSS", rec.division)
        self.assertEqual("Standard", rec.report_category)
        self.assertEqual("BREACHED", rec.sla_status)
        self.assertAlmostEqual(72.0, rec.hours_open)
        self.assertEqual(-1, rec.days_to_target)
        self.assertTrue(rec.is_open)
        self.assertFalse(rec.is_excluded)

    def test_completed_record_is_not_open(self):
        rec = work_order(status="Completed", completed_date=NOW)
        transform_records([rec], as_of=NOW, group_patterns=PATTERNS)
        self.assertFalse(rec.is_open)
        self.assertEqual("MET_TARGET", rec.sla_status)


if __name__ == "__main__":
    unittest.main()
