"""Regression tests for the incremental architecture foundations."""

import ast
import os
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app_core.audit import audit_event as core_audit_event
from app_core.clock import to_workspace, to_workspace_naive
from app_core.settings import AppSettings
from api.auth import audit_event as compatibility_audit_event


ROOT = Path(__file__).resolve().parent.parent


class ArchitectureFoundationTests(unittest.TestCase):
    def test_existing_audit_import_is_a_compatibility_export(self):
        self.assertIs(core_audit_event, compatibility_audit_event)

    def test_division_router_contains_no_sql(self):
        source = (ROOT / "api" / "routers" / "divisions.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "pipeline.db":
                violations.append(f"pipeline.db import at line {node.lineno}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"run_query", "get_cursor"}:
                    violations.append(f"{node.func.id} call at line {node.lineno}")
        self.assertEqual([], violations)

    def test_helix_facade_does_not_own_http_requests(self):
        source_path = ROOT / "helix" / "extractor.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == "requests" for alias in node.names
            ):
                violations.append(f"requests import at line {node.lineno}")
            if isinstance(node, ast.ImportFrom) and node.module == "requests":
                violations.append(f"requests import at line {node.lineno}")
        self.assertEqual([], violations)

    def test_phase_two_email_and_reminder_code_is_not_shipped(self):
        for path in ("notifications", "capabilities/report_delivery",
                     "capabilities/task_reminders", "api/routers/testing_cleanup.py"):
            with self.subTest(path=path):
                self.assertFalse((ROOT / path).exists())

    def test_daily_report_http_and_rendering_adapters_contain_no_sql(self):
        paths = [ROOT / "api" / "routers" / "daily_report.py"]
        violations = []
        for source_path in paths:
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "pipeline.db":
                    violations.append(f"{source_path.name}:{node.lineno}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in {"run_query", "get_cursor"}:
                        violations.append(
                            f"{source_path.name}:{node.lineno}:{node.func.id}"
                        )
        self.assertEqual([], violations)

    def test_daily_report_service_has_no_fastapi_dependency(self):
        source_path = ROOT / "capabilities" / "daily_reports" / "service.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "fastapi"
            ):
                violations.append(f"line {node.lineno}")
            if isinstance(node, ast.Import) and any(
                alias.name.startswith("fastapi") for alias in node.names
            ):
                violations.append(f"line {node.lineno}")
        self.assertEqual([], violations)

    def test_api_routers_do_not_import_each_other(self):
        violations = []
        for source_path in (ROOT / "api" / "routers").glob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and (node.module or "").startswith("api.routers.")
                ):
                    violations.append(
                        f"{source_path.name}:{node.lineno}:{node.module}"
                    )
        self.assertEqual([], violations)

    def test_settings_preserve_existing_environment_contract(self):
        values = {
            "ENVIRONMENT": "QA",
            "WORKSPACE_TIMEZONE": "Africa/Johannesburg",
            "DB_PORT": "5433",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = AppSettings.from_env()
        self.assertEqual("qa", settings.runtime.environment)
        self.assertEqual("Africa/Johannesburg", settings.runtime.workspace_timezone)
        self.assertEqual(5433, settings.database.port)
        self.assertFalse(settings.runtime.runtime_schema_bootstrap_enabled)

    def test_workspace_clock_conversion_preserves_instant(self):
        instant = datetime(2026, 7, 23, 8, 32, tzinfo=UTC)
        local = to_workspace(instant)
        self.assertEqual(ZoneInfo("Africa/Johannesburg"), local.tzinfo)
        self.assertEqual((10, 32), (local.hour, local.minute))
        self.assertEqual(datetime(2026, 7, 23, 10, 32), to_workspace_naive(instant))

    def test_naive_datetimes_remain_workspace_local(self):
        local = datetime(2026, 7, 23, 10, 32)
        self.assertEqual(local, to_workspace_naive(local))


if __name__ == "__main__":
    unittest.main()
