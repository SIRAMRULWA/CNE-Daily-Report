"""Versioned PostgreSQL schema migrations.

The existing idempotent schema is migration 1. Future migrations belong in
``sql/migrations`` and use names such as ``V002__add_delivery_index.sql``.
Applied checksums are immutable so edited production migrations fail loudly.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from pipeline.db import get_cursor, test_connection

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATTERN = re.compile(r"^V(?P<version>\d+)__(?P<name>[a-z0-9_]+)\.sql$")
ADVISORY_LOCK_ID = 1_346_782_901


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_migrations(project_root: Path = PROJECT_ROOT) -> list[Migration]:
    """Return the immutable baseline followed by convention-based migrations."""
    candidates: list[tuple[int, str, Path]] = [
        (1, "baseline", project_root / "sql" / "001_schema.sql")
    ]
    migration_dir = project_root / "sql" / "migrations"
    if migration_dir.exists():
        for path in migration_dir.glob("*.sql"):
            match = MIGRATION_PATTERN.fullmatch(path.name)
            if not match:
                raise ValueError(
                    f"Invalid migration filename {path.name!r}; "
                    "expected VNNN__lowercase_name.sql"
                )
            candidates.append(
                (int(match.group("version")), match.group("name"), path)
            )

    versions: set[int] = set()
    migrations: list[Migration] = []
    for version, name, path in sorted(candidates):
        if not path.is_file():
            raise FileNotFoundError(f"Migration file is missing: {path}")
        if version in versions:
            raise ValueError(f"Duplicate migration version: {version}")
        versions.add(version)
        migrations.append(Migration(version, name, path, _checksum(path)))
    return migrations


def apply_migrations(project_root: Path = PROJECT_ROOT) -> list[int]:
    """Apply pending migrations once under a database-wide advisory lock."""
    migrations = discover_migrations(project_root)
    applied_now: list[int] = []
    with get_cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_ID,))
        cur.execute("CREATE SCHEMA IF NOT EXISTS config")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS config.schema_migrations (
                version       INTEGER PRIMARY KEY,
                name          TEXT NOT NULL,
                checksum      TEXT NOT NULL,
                applied_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                duration_ms   INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            "SELECT version, name, checksum FROM config.schema_migrations"
        )
        applied = {row["version"]: dict(row) for row in cur.fetchall()}

        for migration in migrations:
            previous = applied.get(migration.version)
            if previous:
                if previous["checksum"] != migration.checksum:
                    raise RuntimeError(
                        f"Migration V{migration.version:03d} checksum changed "
                        f"after it was applied ({previous['name']})"
                    )
                continue

            started = time.monotonic()
            cur.execute(migration.path.read_text(encoding="utf-8"))
            duration_ms = max(round((time.monotonic() - started) * 1000), 0)
            cur.execute(
                """
                INSERT INTO config.schema_migrations
                    (version, name, checksum, duration_ms)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    duration_ms,
                ),
            )
            applied_now.append(migration.version)
            logger.info(
                "Applied migration V%03d %s in %dms",
                migration.version,
                migration.name,
                duration_ms,
            )
    return applied_now


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    test_connection()
    applied = apply_migrations()
    if applied:
        logger.info("Database migrations complete: %s", applied)
    else:
        logger.info("Database schema is already current")


if __name__ == "__main__":
    main()
