"""PostgreSQL persistence adapter for divisions and assignee groups."""

from __future__ import annotations

from collections.abc import Iterable

from pipeline.db import get_cursor, run_query


class OrganizationRepository:
    """Own all SQL used by the organization capability."""

    def ensure_storage(self) -> None:
        with get_cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS config")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS config.divisions (
                    name       TEXT PRIMARY KEY,
                    active     BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS config.division_groups (
                    id             BIGSERIAL PRIMARY KEY,
                    division       TEXT NOT NULL,
                    assignee_group TEXT NOT NULL,
                    active         BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    deleted        BOOLEAN NOT NULL DEFAULT FALSE,
                    deleted_by     TEXT,
                    deleted_at     TIMESTAMPTZ,
                    UNIQUE (division, assignee_group)
                )
                """
            )
            cur.execute(
                "ALTER TABLE config.division_groups "
                "ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE"
            )
            cur.execute(
                "ALTER TABLE config.division_groups "
                "ADD COLUMN IF NOT EXISTS deleted_by TEXT"
            )
            cur.execute(
                "ALTER TABLE config.division_groups "
                "ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_division_groups_division "
                "ON config.division_groups(division)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_division_groups_active "
                "ON config.division_groups(active)"
            )

    def upsert_division(self, division: str) -> dict:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO config.divisions (name)
                VALUES (%s)
                ON CONFLICT (name)
                DO UPDATE SET active = TRUE, updated_at = NOW()
                RETURNING name AS division, active, created_at, updated_at
                """,
                (division,),
            )
            return dict(cur.fetchone())

    def upsert_groups(self, division: str, groups: Iterable[str]) -> None:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO config.divisions (name)
                VALUES (%s)
                ON CONFLICT (name)
                DO UPDATE SET active = TRUE, updated_at = NOW()
                """,
                (division,),
            )
            for group in groups:
                cur.execute(
                    """
                    INSERT INTO config.division_groups (division, assignee_group)
                    VALUES (%s, %s)
                    ON CONFLICT (division, assignee_group)
                    DO UPDATE SET
                        active = TRUE,
                        deleted = FALSE,
                        deleted_by = NULL,
                        deleted_at = NULL,
                        updated_at = NOW()
                    """,
                    (division, group),
                )

    def deactivate_group(
        self, division: str, assignee_group: str, deleted_by: str | None
    ) -> bool:
        with get_cursor() as cur:
            cur.execute(
                """
                UPDATE config.division_groups
                SET
                    active = FALSE,
                    deleted = TRUE,
                    deleted_by = %s,
                    deleted_at = NOW(),
                    updated_at = NOW()
                WHERE division = %s AND assignee_group = %s AND active
                """,
                (deleted_by, division, assignee_group),
            )
            return cur.rowcount > 0

    def list_divisions(self) -> list[dict]:
        return run_query(
            """
            SELECT d.name AS division, COUNT(g.id) AS group_count
            FROM config.divisions d
            LEFT JOIN config.division_groups g
              ON g.division = d.name AND g.active AND NOT g.deleted
            WHERE d.active
            GROUP BY d.name
            ORDER BY d.name
            """
        )

    def list_groups(self, division: str | None = None) -> list[dict]:
        if division:
            return run_query(
                """
                SELECT division, assignee_group, active, created_at, updated_at
                FROM config.division_groups
                WHERE active AND NOT deleted AND division = %s
                ORDER BY assignee_group
                """,
                (division,),
            )
        return run_query(
            """
            SELECT division, assignee_group, active, created_at, updated_at
            FROM config.division_groups
            WHERE active AND NOT deleted
            ORDER BY division, assignee_group
            """
        )

