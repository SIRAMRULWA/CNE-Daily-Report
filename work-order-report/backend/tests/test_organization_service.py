"""Database-free tests for organization application behavior."""

import unittest

from capabilities.organization.service import OrganizationService


class FakeOrganizationRepository:
    def __init__(self):
        self.ensured = 0
        self.divisions = {}
        self.groups = {}
        self.fail_reads = False

    def ensure_storage(self):
        self.ensured += 1

    def upsert_division(self, division):
        self.divisions[division] = True
        return {"division": division, "active": True}

    def upsert_groups(self, division, groups):
        self.divisions[division] = True
        for group in groups:
            self.groups[(division, group)] = True

    def deactivate_group(self, division, assignee_group, deleted_by):
        key = (division, assignee_group)
        existed = self.groups.get(key, False)
        self.groups[key] = False
        return existed

    def list_divisions(self):
        return [
            {
                "division": division,
                "group_count": sum(
                    active
                    for (owner, _group), active in self.groups.items()
                    if owner == division
                ),
            }
            for division in sorted(self.divisions)
        ]

    def list_groups(self, division=None):
        if self.fail_reads:
            raise RuntimeError("database unavailable")
        return [
            {"division": owner, "assignee_group": group, "active": True}
            for (owner, group), active in sorted(self.groups.items())
            if active and (division is None or owner == division)
        ]


class OrganizationServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakeOrganizationRepository()
        self.service = OrganizationService(self.repository)

    def test_add_groups_normalizes_and_deduplicates(self):
        rows = self.service.add_groups(
            " INTSS ", [" Team A ", "Team A", "", "Team B"]
        )
        self.assertEqual(["Team A", "Team B"], [row["assignee_group"] for row in rows])
        self.assertIn(("INTSS", "Team A"), self.repository.groups)
        self.assertIn(("INTSS", "Team B"), self.repository.groups)

    def test_deactivate_group_is_a_soft_removal_contract(self):
        self.service.add_groups("INTSS", ["Team A"])
        self.assertTrue(
            self.service.deactivate_group("INTSS", "Team A", "admin@example.com")
        )
        self.assertFalse(
            self.service.deactivate_group("INTSS", "Team A", "admin@example.com")
        )

    def test_group_patterns_fall_back_when_database_is_unavailable(self):
        self.repository.fail_reads = True
        patterns = self.service.load_group_patterns()
        self.assertTrue(patterns)
        self.assertEqual(
            sorted(patterns, key=lambda pair: len(pair[0]), reverse=True), patterns
        )

    def test_blank_division_is_rejected_before_persistence(self):
        with self.assertRaisesRegex(ValueError, "Division is required"):
            self.service.upsert_division(" ")


if __name__ == "__main__":
    unittest.main()
