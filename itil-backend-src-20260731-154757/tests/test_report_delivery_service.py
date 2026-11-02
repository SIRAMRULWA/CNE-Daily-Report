"""Database-free tests for report-delivery application behavior."""

import os
import unittest
from datetime import time
from unittest.mock import MagicMock, patch

from capabilities.report_delivery.errors import (
    ReportDeliveryConflictError,
    ReportDeliveryNotFoundError,
    ReportDeliveryValidationError,
)
from capabilities.report_delivery.service import ReportDeliveryService


class FakeReportDeliveryRepository:
    def __init__(self):
        self.subscriptions = []
        self.updated = None

    def list_subscriptions(self):
        return list(self.subscriptions)

    def create_subscription(self, values, actor):
        row = {"id": 1, **values, "created_by": actor}
        self.subscriptions.append(row)
        return row

    def replace_subscription(self, subscription_id, values, actor):
        if subscription_id != 1:
            return None
        self.updated = {"id": subscription_id, **values, "updated_by": actor}
        return self.updated

    def set_enabled(self, subscription_id, enabled, actor):
        return (
            {"id": subscription_id, "enabled": enabled, "updated_by": actor}
            if subscription_id == 1 else None
        )

    def soft_delete_subscription(self, subscription_id, actor):
        return subscription_id == 1

    def list_deliveries(self, limit):
        return []


class ReportDeliveryServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakeReportDeliveryRepository()
        self.service = ReportDeliveryService(self.repository)
        self.values = {
            "name": "INTSS morning",
            "division": "INTSS",
            "assignee_group": None,
            "recipients": ["team@vodacom.co.za"],
            "cc_recipients": [],
            "frequency": "DAILY",
            "weekday": None,
            "send_time": time(8, 0),
            "timezone": "Africa/Johannesburg",
            "attachment_format": "XLSX",
            "enabled": False,
        }

    def organization(self):
        service = MagicMock()
        service.list_groups.return_value = [
            {"division": "INTSS", "assignee_group": "Team A"}
        ]
        return service

    @patch("capabilities.report_delivery.service.audit_event")
    @patch("capabilities.report_delivery.service.get_organization_service")
    def test_create_subscription_uses_repository_and_audits(
        self, organization_factory, audit
    ):
        organization_factory.return_value = self.organization()
        row = self.service.create_subscription(
            self.values, "admin@vodacom.co.za"
        )
        self.assertEqual(1, row["id"])
        self.assertEqual("admin@vodacom.co.za", row["created_by"])
        audit.assert_called_once()

    @patch("capabilities.report_delivery.service.get_organization_service")
    def test_scope_validation_rejects_unknown_group(self, organization_factory):
        organization_factory.return_value = self.organization()
        with self.assertRaises(ReportDeliveryValidationError):
            self.service.validate_scope("INTSS", "Missing Team")

    def test_external_recipient_policy_is_preserved(self):
        with patch.dict(
            os.environ,
            {
                "REPORT_EMAIL_ALLOW_EXTERNAL": "false",
                "REPORT_EMAIL_ALLOWED_DOMAINS": "vodacom.co.za",
            },
            clear=True,
        ):
            with self.assertRaises(ReportDeliveryValidationError):
                self.service.validate_recipient_policy(["person@example.com"])

    def test_enabling_requires_approval(self):
        with patch.dict(
            os.environ, {"REPORT_EMAIL_AUTOMATION_APPROVED": "false"}, clear=True
        ):
            with self.assertRaises(ReportDeliveryConflictError):
                self.service.set_subscription_enabled(
                    1, True, "admin@vodacom.co.za"
                )

    def test_missing_subscription_is_reported(self):
        with self.assertRaises(ReportDeliveryNotFoundError):
            self.service.delete_subscription(999, "admin@vodacom.co.za")


if __name__ == "__main__":
    unittest.main()
