"""Application service for division and assignee-group management."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Protocol

from app_core.settings import env_flag
from config.mappings import DEFAULT_DIVISION_GROUPS, GROUP_PATTERNS

logger = logging.getLogger(__name__)


class OrganizationStore(Protocol):
    def ensure_storage(self) -> None: ...
    def upsert_division(self, division: str) -> dict: ...
    def upsert_groups(self, division: str, groups: Iterable[str]) -> None: ...
    def deactivate_group(
        self, division: str, assignee_group: str, deleted_by: str | None
    ) -> bool: ...
    def list_divisions(self) -> list[dict]: ...
    def list_groups(self, division: str | None = None) -> list[dict]: ...


class OrganizationService:
    def __init__(self, repository: OrganizationStore):
        self.repository = repository

    def ensure_storage(self) -> None:
        self.repository.ensure_storage()

    def _legacy_bootstrap(self) -> None:
        if env_flag("RUNTIME_SCHEMA_BOOTSTRAP_ENABLED", False):
            self.ensure_storage()

    def seed_defaults(self) -> None:
        self._legacy_bootstrap()
        for division, groups in DEFAULT_DIVISION_GROUPS.items():
            self.repository.upsert_groups(division, groups)

    def upsert_division(self, division: str) -> dict:
        self._legacy_bootstrap()
        return self.repository.upsert_division(self._division(division))

    def add_groups(self, division: str, groups: Iterable[str]) -> list[dict]:
        self._legacy_bootstrap()
        name = self._division(division)
        normalized = self._groups(groups)
        if not normalized:
            return []
        self.repository.upsert_groups(name, normalized)
        return self.repository.list_groups(name)

    def deactivate_group(
        self, division: str, assignee_group: str, deleted_by: str | None = None
    ) -> bool:
        self._legacy_bootstrap()
        return self.repository.deactivate_group(
            self._division(division), assignee_group.strip(), deleted_by
        )

    def list_divisions(self) -> list[dict]:
        self._legacy_bootstrap()
        return self.repository.list_divisions()

    def list_groups(self, division: str | None = None) -> list[dict]:
        self._legacy_bootstrap()
        return self.repository.list_groups(division.strip() if division else None)

    def load_group_patterns(self) -> list[tuple[str, str]]:
        try:
            rows = self.list_groups()
        except Exception as exc:
            logger.warning(
                "Could not load DB division groups, using static mappings: %s", exc
            )
            rows = []

        configured = [(row["assignee_group"], row["division"]) for row in rows]
        defaults = list(GROUP_PATTERNS)
        for division, groups in DEFAULT_DIVISION_GROUPS.items():
            defaults.extend((group, division) for group in groups)
        deduplicated = list(dict.fromkeys(configured + defaults))
        return sorted(deduplicated, key=lambda pair: len(pair[0]), reverse=True)

    def load_target_groups(self) -> list[str]:
        return [pattern for pattern, _division in self.load_group_patterns()]

    @staticmethod
    def _division(value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Division is required")
        return name

    @staticmethod
    def _groups(groups: Iterable[str]) -> list[str]:
        normalized = [group.strip() for group in groups if group and group.strip()]
        return list(dict.fromkeys(normalized))
