"""
api/routers/auth.py
===================
Login, logout, current-user, and Super Admin user-management endpoints.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from api.auth import (
    AccountStatus,
    AuthenticatedUser,
    Role,
    audit_event,
    client_ip,
    corporate_email,
    create_access_token,
    get_user_by_email,
    hash_password,
    parse_user_agent,
    record_login_history,
    require_current_user,
    require_roles,
    utcnow,
    verify_password,
)
from pipeline.db import get_cursor, run_query



class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1)

    @field_validator("password")
    @classmethod
    def clean_password(cls, value: str) -> str:
        return value.strip()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: "AuthenticatedUserResponse"


class AuthenticatedUserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None = None
    role: Role
    status: AccountStatus
    must_change_password: bool


class CreateUserRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    full_name: str | None = Field(default=None, max_length=200)
    password: str = Field(..., min_length=12)
    role: Role = Role.USER

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return corporate_email(value)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: Role) -> Role:
        if value == Role.SUPER_ADMIN:
            raise ValueError("SUPER_ADMIN is reserved for the configured system owner")
        return value

    @field_validator("password")
    @classmethod
    def clean_password(cls, value: str) -> str:
        return value.strip()


class StatusUpdateRequest(BaseModel):
    status: AccountStatus


class RoleUpdateRequest(BaseModel):
    role: Role

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: Role) -> Role:
        if value == Role.SUPER_ADMIN:
            raise ValueError("SUPER_ADMIN is reserved for the configured system owner")
        return value


class PasswordResetRequest(BaseModel):
    password: str = Field(..., min_length=12)
    must_change_password: bool = True

    @field_validator("password")
    @classmethod
    def clean_password(cls, value: str) -> str:
        return value.strip()


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12)

    @field_validator("current_password", "new_password")
    @classmethod
    def clean_passwords(cls, value: str) -> str:
        return value.strip()


UserIdPath = int


def user_response(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "full_name": row.get("full_name"),
        "role": row["role"],
        "status": row["status"],
        "must_change_password": row.get("must_change_password"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "last_login_at": row.get("last_login_at"),
    }


def login(payload: LoginRequest, request: Request):
    email = str(payload.email).strip().lower()
    user = get_user_by_email(email)
    if not user:
        # Equalize most of the password-processing cost and return the same
        # public error as an incorrect password to reduce account enumeration.
        hash_password(payload.password)
        record_login_history(email=email, status_text="FAILED", request=request, failure_reason="USER_NOT_FOUND")
        audit_event(
            action="failed_login",
            entity_type="user",
            entity_id=email,
            actor=email,
            request=request,
            result="FAILED",
            details={"reason": "USER_NOT_FOUND"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not verify_password(payload.password, user["password_hash"]):
        record_login_history(
            email=email,
            status_text="FAILED",
            request=request,
            user_id=user["id"],
            failure_reason="BAD_PASSWORD",
        )
        audit_event(
            action="failed_login",
            entity_type="user",
            entity_id=email,
            actor=email,
            request=request,
            result="FAILED",
            details={"reason": "BAD_PASSWORD"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user["status"] != AccountStatus.ACTIVE:
        record_login_history(
            email=email,
            status_text="FAILED",
            request=request,
            user_id=user["id"],
            failure_reason=f"ACCOUNT_{user['status']}",
        )
        audit_event(
            action="failed_login",
            entity_type="user",
            entity_id=email,
            actor=email,
            request=request,
            result="FAILED",
            details={"reason": f"ACCOUNT_{user['status']}"},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")

    session_id = secrets.token_urlsafe(32)
    token_jti = secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(minutes=480)
    user_agent = request.headers.get("user-agent")
    browser, os_name = parse_user_agent(user_agent)

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO config.user_sessions
                (id, user_id, token_jti, expires_at, ip_address, user_agent, browser, operating_system)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (session_id, user["id"], token_jti, expires_at, client_ip(request), user_agent, browser, os_name),
        )
        cur.execute("UPDATE config.users SET last_login_at = NOW(), updated_at = NOW() WHERE id = %s", (user["id"],))

    record_login_history(email=email, status_text="SUCCESS", request=request, user_id=user["id"])
    audit_event(
        action="user_logged_in",
        entity_type="user",
        entity_id=email,
        actor=email,
        request=request,
        details={"session_id": session_id},
    )
    return {
        "access_token": create_access_token(user, session_id=session_id, token_jti=token_jti, expires_at=expires_at),
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name"),
            "role": user["role"],
            "status": user["status"],
            "must_change_password": user["must_change_password"],
        },
    }


def logout(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_current_user),
):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE config.user_sessions
            SET revoked_at = NOW(), revoked_by = %s, status = 'REVOKED'
            WHERE id = %s AND revoked_at IS NULL
            """,
            (current_user.email, current_user.session_id),
        )
    audit_event(
        action="user_logged_out",
        entity_type="user_session",
        entity_id=current_user.session_id,
        actor=current_user.email,
        request=request,
    )
    return {"status": "ok"}


def me(current_user: AuthenticatedUser = Depends(require_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "display_name": current_user.email.split(".")[0] + " " + current_user.email.split(".")[1].split("@")[0],
        "role": current_user.role,
        "status": current_user.status,
        "must_change_password": current_user.must_change_password,
        "session_id": current_user.session_id,
    }


def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_current_user),
):
    rows = run_query(
        "SELECT password_hash FROM config.users WHERE id = %s AND deleted = FALSE",
        (current_user.id,),
    )
    if not rows or not verify_password(payload.current_password, rows[0]["password_hash"]):
        audit_event(
            action="password_change_failed",
            entity_type="user",
            entity_id=current_user.email,
            actor=current_user.email,
            request=request,
            result="FAILED",
            details={"reason": "BAD_CURRENT_PASSWORD"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE config.users
            SET password_hash = %s, must_change_password = FALSE, updated_at = NOW()
            WHERE id = %s
            """,
            (hash_password(payload.new_password), current_user.id),
        )
        cur.execute(
            """
            UPDATE config.user_sessions
            SET revoked_at = NOW(), revoked_by = %s, status = 'REVOKED'
            WHERE user_id = %s AND id <> %s AND revoked_at IS NULL
            """,
            (current_user.email, current_user.id, current_user.session_id),
        )
    audit_event(
        action="password_changed",
        entity_type="user",
        entity_id=current_user.email,
        actor=current_user.email,
        request=request,
    )
    return {"status": "ok"}


def list_users(
    status_filter: AccountStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
):
    conditions = ["deleted = FALSE"]
    params: list = []
    if status_filter:
        conditions.append("status = %s")
        params.append(status_filter)
    params.extend([limit, offset])
    rows = run_query(
        f"""
        SELECT id, email, full_name, role, status, must_change_password, created_at, updated_at, last_login_at
        FROM config.users
        WHERE {" AND ".join(conditions)}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    )
    return {"users": [user_response(row) for row in rows], "count": len(rows), "limit": limit, "offset": offset}


def create_user(
    payload: CreateUserRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_roles(Role.SUPER_ADMIN)),
):
    email = corporate_email(str(payload.email))
    existing_rows = run_query(
        "SELECT id, email, deleted FROM config.users WHERE LOWER(email) = %s",
        (email,),
    )
    existing = existing_rows[0] if existing_rows else None
    if existing:
        if not existing["deleted"]:
            raise HTTPException(status_code=409, detail="User already exists")
        with get_cursor() as cur:
            cur.execute(
                """
                UPDATE config.users
                SET full_name = %s,
                    password_hash = %s,
                    role = %s,
                    status = 'ACTIVE',
                    must_change_password = TRUE,
                    deleted = FALSE,
                    deleted_by = NULL,
                    deleted_at = NULL,
                    disabled_by = NULL,
                    disabled_at = NULL,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, email, full_name, role, status, must_change_password, created_at, updated_at, last_login_at
                """,
                (payload.full_name, hash_password(payload.password), payload.role, existing["id"]),
            )
            row = dict(cur.fetchone())
        audit_event(
            action="user_reactivated",
            entity_type="user",
            entity_id=email,
            actor=current_user.email,
            request=request,
            details={"role": payload.role},
        )
        return user_response(row)
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO config.users
                (email, full_name, password_hash, role, status, must_change_password, created_by)
            VALUES (%s, %s, %s, %s, 'ACTIVE', TRUE, %s)
            RETURNING id, email, full_name, role, status, must_change_password, created_at, updated_at, last_login_at
            """,
            (email, payload.full_name, hash_password(payload.password), payload.role, current_user.email),
        )
        row = dict(cur.fetchone())
    audit_event(
        action="user_created",
        entity_type="user",
        entity_id=email,
        actor=current_user.email,
        request=request,
        details={"role": payload.role},
    )
    return user_response(row)


def delete_user(
    request: Request,
    user_id: UserIdPath = Path(..., ge=1),
    current_user: AuthenticatedUser = Depends(require_roles(Role.SUPER_ADMIN)),
):
    rows = run_query("SELECT id, email, role FROM config.users WHERE id = %s AND deleted = FALSE", (user_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="User not found")

    target = rows[0]
    if target["id"] == current_user.id:
        raise HTTPException(status_code=403, detail="You cannot delete your own account")
    if target["role"] == Role.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="The configured Super Admin cannot be deleted")

    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE config.users
            SET status = 'DISABLED',
                deleted = TRUE,
                deleted_by = %s,
                deleted_at = NOW(),
                disabled_by = %s,
                disabled_at = NOW(),
                updated_at = NOW()
            WHERE id = %s AND deleted = FALSE
            RETURNING id, email
            """,
            (current_user.email, current_user.email, user_id),
        )
        row = cur.fetchone()
        cur.execute(
            """
            UPDATE config.user_sessions
            SET revoked_at = NOW(), revoked_by = %s, status = 'REVOKED'
            WHERE user_id = %s AND revoked_at IS NULL
            """,
            (current_user.email, user_id),
        )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    deleted_user = dict(row)
    audit_event(
        action="user_deleted",
        entity_type="user",
        entity_id=deleted_user["email"],
        actor=current_user.email,
        request=request,
        details={"user_id": deleted_user["id"]},
    )
    return {"id": deleted_user["id"], "email": deleted_user["email"], "deleted": True}


def update_user_status(
    payload: StatusUpdateRequest,
    request: Request,
    user_id: UserIdPath = Path(..., ge=1),
    current_user: AuthenticatedUser = Depends(require_roles(Role.SUPER_ADMIN)),
):
    rows = run_query("SELECT id, email, role FROM config.users WHERE id = %s AND deleted = FALSE", (user_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="User not found")
    if rows[0]["role"] == Role.SUPER_ADMIN and rows[0]["email"].lower() != current_user.email.lower():
        raise HTTPException(status_code=403, detail="The configured Super Admin cannot be managed by another user")

    disabled_by = current_user.email if payload.status == AccountStatus.DISABLED else None
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE config.users
            SET status = %s,
                disabled_by = %s,
                disabled_at = CASE WHEN %s = 'DISABLED' THEN NOW() ELSE NULL END,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, email, full_name, role, status, must_change_password, created_at, updated_at, last_login_at
            """,
            (payload.status, disabled_by, payload.status, user_id),
        )
        row = dict(cur.fetchone())
    if payload.status != AccountStatus.ACTIVE:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE config.user_sessions SET revoked_at = NOW(), revoked_by = %s, status = 'REVOKED' WHERE user_id = %s",
                (current_user.email, user_id),
            )
    audit_event(
        action="user_status_changed",
        entity_type="user",
        entity_id=row["email"],
        actor=current_user.email,
        request=request,
        details={"status": payload.status},
    )
    return user_response(row)


def update_user_role(
    payload: RoleUpdateRequest,
    request: Request,
    user_id: UserIdPath = Path(..., ge=1),
    current_user: AuthenticatedUser = Depends(require_roles(Role.SUPER_ADMIN)),
):
    rows = run_query("SELECT id, email, role FROM config.users WHERE id = %s AND deleted = FALSE", (user_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="User not found")
    if rows[0]["role"] == Role.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="The configured Super Admin role cannot be reassigned")
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE config.users
            SET role = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, email, full_name, role, status, must_change_password, created_at, updated_at, last_login_at
            """,
            (payload.role, user_id),
        )
        row = dict(cur.fetchone())
    audit_event(
        action="user_role_changed",
        entity_type="user",
        entity_id=row["email"],
        actor=current_user.email,
        request=request,
        details={"role": payload.role},
    )
    return user_response(row)


def reset_password(
    payload: PasswordResetRequest,
    request: Request,
    user_id: UserIdPath = Path(..., ge=1),
    current_user: AuthenticatedUser = Depends(require_roles(Role.SUPER_ADMIN)),
):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE config.users
            SET password_hash = %s, must_change_password = %s, updated_at = NOW()
            WHERE id = %s AND deleted = FALSE
            RETURNING id, email, full_name, role, status, must_change_password, created_at, updated_at, last_login_at
            """,
            (hash_password(payload.password), payload.must_change_password, user_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    row = dict(row)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE config.user_sessions SET revoked_at = NOW(), revoked_by = %s, status = 'REVOKED' WHERE user_id = %s",
            (current_user.email, user_id),
        )
    audit_event(
        action="password_reset",
        entity_type="user",
        entity_id=row["email"],
        actor=current_user.email,
        request=request,
    )
    return user_response(row)


def login_history(limit: int = Query(default=100, le=1000), offset: int = Query(default=0, ge=0)):
    rows = run_query(
        """
        SELECT
            lh.id,
            lh.email,
            u.full_name,
            lh.login_time,
            lh.ip_address,
            lh.browser,
            lh.operating_system,
            lh.status,
            lh.failure_reason
        FROM config.login_history lh
        LEFT JOIN config.users u ON u.id = lh.user_id
        ORDER BY lh.login_time DESC, lh.id DESC
        LIMIT %s OFFSET %s
        """,
        (limit, offset),
    )
    return {"logins": rows, "count": len(rows), "limit": limit, "offset": offset}


def active_sessions(limit: int = Query(default=100, le=1000), offset: int = Query(default=0, ge=0)):
    rows = run_query(
        """
        SELECT
            s.id,
            u.email,
            u.full_name,
            s.issued_at,
            s.expires_at,
            s.revoked_at,
            s.ip_address,
            s.browser,
            s.operating_system,
            s.status
        FROM config.user_sessions s
        JOIN config.users u ON u.id = s.user_id
        ORDER BY s.issued_at DESC
        LIMIT %s OFFSET %s
        """,
        (limit, offset),
    )
    return {"sessions": rows, "count": len(rows), "limit": limit, "offset": offset}


def revoke_session(
    request: Request,
    session_id: str,
    current_user: AuthenticatedUser = Depends(require_roles(Role.SUPER_ADMIN)),
):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE config.user_sessions
            SET revoked_at = NOW(), revoked_by = %s, status = 'REVOKED'
            WHERE id = %s AND revoked_at IS NULL
            RETURNING id
            """,
            (current_user.email, session_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Active session not found")
    audit_event(
        action="session_revoked",
        entity_type="user_session",
        entity_id=session_id,
        actor=current_user.email,
        request=request,
    )
    return {"session_id": session_id, "status": "REVOKED"}
