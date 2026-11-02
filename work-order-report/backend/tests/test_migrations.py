"""Database-free tests for versioned migration discovery and deployment wiring."""

import tempfile
import unittest
from pathlib import Path

from app_core.migrations import discover_migrations


ROOT = Path(__file__).resolve().parent.parent


class MigrationTests(unittest.TestCase):
    def test_repository_baseline_is_migration_one(self):
        migrations = discover_migrations(ROOT)
        self.assertEqual(1, migrations[0].version)
        self.assertEqual("baseline", migrations[0].name)
        self.assertEqual("001_schema.sql", migrations[0].path.name)
        self.assertEqual(64, len(migrations[0].checksum))

    def test_future_migrations_are_ordered_by_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sql" / "migrations").mkdir(parents=True)
            (root / "sql" / "001_schema.sql").write_text(
                "SELECT 1;", encoding="utf-8"
            )
            (root / "sql" / "migrations" / "V003__third.sql").write_text(
                "SELECT 3;", encoding="utf-8"
            )
            (root / "sql" / "migrations" / "V002__second.sql").write_text(
                "SELECT 2;", encoding="utf-8"
            )
            self.assertEqual(
                [1, 2, 3],
                [migration.version for migration in discover_migrations(root)],
            )

    def test_duplicate_versions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sql" / "migrations").mkdir(parents=True)
            (root / "sql" / "001_schema.sql").write_text(
                "SELECT 1;", encoding="utf-8"
            )
            (root / "sql" / "migrations" / "V001__duplicate.sql").write_text(
                "SELECT 2;", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "Duplicate migration"):
                discover_migrations(root)

    def test_invalid_migration_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sql" / "migrations").mkdir(parents=True)
            (root / "sql" / "001_schema.sql").write_text(
                "SELECT 1;", encoding="utf-8"
            )
            (root / "sql" / "migrations" / "002_bad.sql").write_text(
                "SELECT 2;", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "Invalid migration filename"):
                discover_migrations(root)

    def test_deployment_uses_migration_runner(self):
        script = (ROOT / "deploy" / "init-db.sh").read_text(encoding="utf-8")
        self.assertIn("python -m app_core.migrations", script)
        self.assertNotIn('execute_sql_file("sql/001_schema.sql")', script)
        startup = (ROOT / "deploy" / "start-api.sh").read_text(encoding="utf-8")
        self.assertLess(
            startup.index("python -m app_core.migrations"),
            startup.index("exec uvicorn"),
        )
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn('CMD ["bash", "deploy/start-api.sh"]', dockerfile)

    def test_release_package_contains_architecture_modules(self):
        script = (ROOT / "deploy" / "package-release.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('"app_core"', script)
        self.assertIn('"capabilities"', script)


if __name__ == "__main__":
    unittest.main()
