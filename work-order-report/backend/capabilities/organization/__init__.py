"""Division and assignee-group organization capability."""

from functools import lru_cache

from capabilities.organization.repository import OrganizationRepository
from capabilities.organization.service import OrganizationService


@lru_cache(maxsize=1)
def get_organization_service() -> OrganizationService:
    return OrganizationService(OrganizationRepository())


__all__ = ["OrganizationRepository", "OrganizationService", "get_organization_service"]

