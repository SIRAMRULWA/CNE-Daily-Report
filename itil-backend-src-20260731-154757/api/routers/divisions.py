"""
api/routers/divisions.py
========================
Editable division and assignee-group mapping endpoints.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field, field_validator

from api.auth import AuthenticatedUser, Role, audit_event, require_at_least
from capabilities.organization import get_organization_service



class DivisionCreate(BaseModel):
    division: str = Field(..., min_length=1, examples=["CVDI"])

    @field_validator("division")
    @classmethod
    def clean_division(cls, value: str) -> str:
        return value.strip()


class DivisionGroupsCreate(BaseModel):
    groups: list[str] = Field(
        ...,
        min_length=1,
        examples=[["Appl:VAS SMS:OSS", "Appl:VAS MMS:OSS"]],
    )

    @field_validator("groups")
    @classmethod
    def clean_groups(cls, value: list[str]) -> list[str]:
        groups = [group.strip() for group in value if group and group.strip()]
        if not groups:
            raise ValueError("At least one non-empty group is required")
        return groups


DivisionPath = Annotated[str, Path(min_length=1, examples=["OSS"])]
GroupPath = Annotated[str, Path(min_length=1, examples=["Appl:VAS SMS:OSS"])]


def get_divisions():
    """List active divisions and their group counts."""
    rows = get_organization_service().list_divisions()
    return {"divisions": rows, "count": len(rows)}


def create_division(
    payload: DivisionCreate,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    """Create or reactivate a division."""
    row = get_organization_service().upsert_division(payload.division)
    audit_event(
        action="upsert_division",
        entity_type="division",
        entity_id=payload.division,
        actor=current_user.email,
        request=request,
        details={"division": payload.division},
    )
    return row


def get_division_groups(division: DivisionPath):
    """List active assignee groups mapped to one division."""
    rows = get_organization_service().list_groups(division=division)
    return {"division": division, "groups": rows, "count": len(rows)}


def create_division_groups(
    division: DivisionPath,
    payload: DivisionGroupsCreate,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    """Add or reactivate one or more assignee groups under a division."""
    rows = get_organization_service().add_groups(division=division, groups=payload.groups)
    audit_event(
        action="add_division_groups",
        entity_type="division",
        entity_id=division,
        actor=current_user.email,
        request=request,
        details={"division": division, "groups": payload.groups},
    )
    return {"division": division, "groups": rows, "count": len(rows)}


def delete_division_group(
    division: DivisionPath,
    assignee_group: GroupPath,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    """Deactivate one assignee-group mapping."""
    removed = get_organization_service().deactivate_group(
        division=division,
        assignee_group=assignee_group,
        deleted_by=current_user.email,
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Division group mapping not found")
    audit_event(
        action="deactivate_division_group",
        entity_type="division_group",
        entity_id=f"{division}:{assignee_group}",
        actor=current_user.email,
        request=request,
        details={"division": division, "assignee_group": assignee_group},
    )
    return {"division": division, "assignee_group": assignee_group, "active": False}


def seed_default_groups(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_at_least(Role.ADMIN)),
):
    """Seed the built-in NSD, CDN, CVDI, and INTSS mappings."""
    service = get_organization_service()
    service.seed_defaults()
    audit_event(
        action="seed_default_division_groups",
        entity_type="division_groups",
        actor=current_user.email,
        request=request,
    )
    rows = service.list_divisions()
    return {"divisions": rows, "count": len(rows)}
