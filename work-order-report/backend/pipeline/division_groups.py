"""Compatibility facade for the organization capability.

Existing imports remain supported while persistence and business behavior are
owned by ``capabilities.organization``.
"""

from collections.abc import Iterable

from capabilities.organization import get_organization_service


def ensure_division_groups_table() -> None:
    get_organization_service().ensure_storage()


def seed_default_division_groups() -> None:
    get_organization_service().seed_defaults()


def add_division_groups(division: str, groups: Iterable[str]) -> list[dict]:
    return get_organization_service().add_groups(division, groups)


def upsert_division(division: str) -> dict:
    return get_organization_service().upsert_division(division)


def deactivate_division_group(
    division: str, assignee_group: str, deleted_by: str | None = None
) -> bool:
    return get_organization_service().deactivate_group(
        division, assignee_group, deleted_by
    )


def list_divisions() -> list[dict]:
    return get_organization_service().list_divisions()


def list_division_groups(division: str | None = None) -> list[dict]:
    return get_organization_service().list_groups(division)


def load_group_patterns() -> list[tuple[str, str]]:
    return get_organization_service().load_group_patterns()


def load_target_groups() -> list[str]:
    return get_organization_service().load_target_groups()
