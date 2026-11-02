"""Database-free tests for Task Reminder application behavior."""

import unittest
from datetime import time
from unittest.mock import MagicMock, patch

from capabilities.task_reminders.errors import (
    TaskReminderConflictError,
    TaskReminderNotFoundError,
    TaskReminderValidationError,
)
from capabilities.task_reminders.service import TaskReminderService


class FakeTaskReminderRepository:
    def __init__(self):
        self.subscription = None
        self.execution = {"id": 90, "status": "RUNNING"}

    def list_subscriptions(self, limit, offset):
        return [self.subscription] if self.subscription else []

    def list_enabled_subscriptions(self):
        return (
            [self.subscription]
            if self.subscription and self.subscription["enabled"]
            else []
        )

    def get_subscription(self, subscription_id):
        if self.subscription and self.subscription["id"] == subscription_id:
            return self.subscription
        return None

    def create_subscription(self, values, actor):
        self.subscription = {"id": 1, **values, "created_by": actor}
        return self.subscription

    def replace_subscription(self, subscription_id, values, actor):
        if not self.subscription or self.subscription["id"] != subscription_id:
            return None
        self.subscription = {"id": subscription_id, **values, "updated_by": actor}
        return self.subscription

    def set_enabled(self, subscription_id, enabled, actor):
        if not self.subscription or self.subscription["id"] != subscription_id:
            return None
        self.subscription["enabled"] = enabled
        return self.subscription

    def soft_delete(self, subscription_id, actor):
        return bool(
            self.subscription and self.subscription["id"] == subscription_id
        )

    def list_executions(self, subscription_id, status, limit, offset):
        return []

    def claim_execution(
        self, subscription_id, idempotency_key, trigger_source,
        recipients, requested_by,
    ):
        return self.execution, True


class TaskReminderServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakeTaskReminderRepository()
        self.service = TaskReminderService(self.repository)
        self.values = {
            "name": "INTSS follow-up",
            "division": "INTSS",
            "assignee_group": None,
            "recipients": ["team@vodacom.co.za"],
            "cc_recipients": [],
            "subject": None,
            "frequency": "DAILY",
            "weekday": None,
            "send_time": time(10, 0),
            "timezone": "Africa/Johannesburg",
            "max_records": 10000,
            "enabled": False,
        }

    @staticmethod
    def organization():
        organization = MagicMock()
        organization.list_groups.return_value = [
            {"division": "INTSS", "assignee_group": "Team A"}
        ]
        return organization

    @patch("capabilities.task_reminders.service.audit_event")
    @patch("capabilities.task_reminders.service.get_organization_service")
    def test_create_subscription_validates_and_audits(
        self, organization_factory, audit
    ):
        organization_factory.return_value = self.organization()
        row = self.service.create_subscription(
            self.values, "admin@vodacom.co.za"
        )
        self.assertEqual(1, row["id"])
        audit.assert_called_once()

    @patch("capabilities.task_reminders.service.get_organization_service")
    def test_unknown_group_is_rejected(self, organization_factory):
        organization_factory.return_value = self.organization()
        values = {**self.values, "assignee_group": "Missing Team"}
        with self.assertRaises(TaskReminderValidationError):
            self.service.create_subscription(values, "admin@vodacom.co.za")

    def test_disabled_subscription_cannot_execute(self):
        self.repository.subscription = {"id": 1, **self.values}
        with self.assertRaises(TaskReminderConflictError):
            self.service.execute(1, "manual-12345678", "MANUAL", "admin")

    def test_missing_subscription_is_reported(self):
        with self.assertRaises(TaskReminderNotFoundError):
            self.service.execute(999, "manual-12345678", "MANUAL", "admin")

    def test_duplicate_execution_returns_existing_without_helix_call(self):
        self.repository.subscription = {"id": 1, **self.values, "enabled": True}
        result = self.service.execute(
            1, "scheduled-2026-07-28-1000", "AUTOMATION", "scheduler"
        )
        self.assertTrue(result["duplicate"])
        self.assertEqual(90, result["id"])


if __name__ == "__main__":
    unittest.main()
