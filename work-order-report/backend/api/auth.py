"""
api/auth.py
===========
Authentication, authorization, sessions, and audit helpers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg2.extras import Json

from app_core.audit import audit_event, client_ip, parse_user_agent
from pipeline.db import get_cursor, run_query

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

DEFAULT_CORPORATE_EMAIL_DOMAINS = {"vodacom.co.za", "vodacom.com", "vcontractor.co.za"}
DEFAULT_ACCESS_TOKEN_MINUTES = 8 * 60


class Role(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    USER = "USER"
    READ_ONLY = "READ_ONLY"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    LOCKED = "LOCKED"


ROLE_RANK = {
    Role.READ_ONLY: 10,
    Role.USER: 20,
    Role.MANAGER: 30,
    Role.ADMIN: 40,
    Role.SUPER_ADMIN: 50,
}


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    email: str
    role: Role
    status: AccountStatus
    must_change_password: bool
    session_id: str


def utcnow() -> datetime:
    return datetime.now(UTC)


def configured_super_admin_email() -> str:
    return os.getenv("SUPER_ADMIN_EMAIL", "siphamandla.mdletshe@vcontractor.co.za").strip().strip("'\"").lower()


def allowed_email_domains() -> set[str]:
    configured = os.getenv("AUTH_ALLOWED_EMAIL_DOMAINS", "").strip()
    if not configured:
        return DEFAULT_CORPORATE_EMAIL_DOMAINS
    return {
        domain.strip().lower()
        for domain in configured.split(",")
        if domain.strip()
    }


def jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if secret:
        return secret
    if os.getenv("ENVIRONMENT", "dev").lower() in {"prod", "production"}:
        raise RuntimeError("JWT_SECRET must be set in production")
    return "dev-only-change-me"


def corporate_email(email: str) -> str:
    cleaned = email.strip().strip("'\"").lower()
    domain = cleaned.rsplit("@", 1)[-1] if "@" in cleaned else ""
    if domain not in allowed_email_domains():
        raise ValueError(
            "Only approved corporate email addresses are allowed. "
            "Configure AUTH_ALLOWED_EMAIL_DOMAINS to change the allow-list."
        )
    return cleaned


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 390_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = _b64url_decode(salt_text)
        expected = _b64url_decode(digest_text)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_access_token(user: dict, session_id: str, token_jti: str, expires_at: datetime) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "sid": session_id,
        "jti": token_jti,
        "iat": int(utcnow().timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_text, payload_text, signature_text = token.split(".", 2)
        signing_input = f"{header_text}.{payload_text}"
        expected = hmac.new(jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_decode(signature_text), expected):
            raise ValueError("Invalid token signature")
        payload = json.loads(_b64url_decode(payload_text))
        if int(payload.get("exp", 0)) < int(utcnow().timestamp()):
            raise ValueError("Token expired")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        ) from exc


def ensure_auth_tables() -> None:
    with get_cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS config")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS config.users (
                id BIGSERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('SUPER_ADMIN','ADMIN','MANAGER','USER','READ_ONLY')),
                status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED','LOCKED')),
                must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_login_at TIMESTAMPTZ,
                disabled_by TEXT,
                disabled_at TIMESTAMPTZ,
                deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_by TEXT,
                deleted_at TIMESTAMPTZ
            )
            """
        )
        cur.execute("ALTER TABLE config.users ADD COLUMN IF NOT EXISTS full_name TEXT")
        cur.execute("ALTER TABLE config.users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE")
        cur.execute("ALTER TABLE config.users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE config.users ADD COLUMN IF NOT EXISTS disabled_by TEXT")
        cur.execute("ALTER TABLE config.users ADD COLUMN IF NOT EXISTS disabled_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE config.users ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE config.users ADD COLUMN IF NOT EXISTS deleted_by TEXT")
        cur.execute("ALTER TABLE config.users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_single_super_admin "
            "ON config.users ((role)) WHERE role = 'SUPER_ADMIN' AND deleted = FALSE"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON config.users(LOWER(email))")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON config.users(status)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS config.user_sessions (
                id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES config.users(id),
                token_jti TEXT NOT NULL UNIQUE,
                issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                revoked_at TIMESTAMPTZ,
                revoked_by TEXT,
                ip_address TEXT,
                user_agent TEXT,
                browser TEXT,
                operating_system TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','REVOKED','EXPIRED'))
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON config.user_sessions(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_status ON config.user_sessions(status)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS config.login_history (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES config.users(id),
                email TEXT NOT NULL,
                login_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ip_address TEXT,
                user_agent TEXT,
                browser TEXT,
                operating_system TEXT,
                status TEXT NOT NULL CHECK (status IN ('SUCCESS','FAILED')),
                failure_reason TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_login_history_time ON config.login_history(login_time DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_login_history_email ON config.login_history(LOWER(email))")


def ensure_super_admin_user(*, ensure_schema: bool = True) -> None:
    if ensure_schema:
        ensure_auth_tables()
    email = corporate_email(configured_super_admin_email())
    rows = run_query("SELECT id, email, role FROM config.users WHERE LOWER(email) = %s AND deleted = FALSE", (email,))
    super_admin_rows = run_query(
        "SELECT id, email FROM config.users WHERE role = 'SUPER_ADMIN' AND deleted = FALSE",
    )
    if rows:
        if rows[0]["role"] != Role.SUPER_ADMIN:
            if super_admin_rows and super_admin_rows[0]["id"] != rows[0]["id"]:
                raise RuntimeError(
                    "Configured SUPER_ADMIN_EMAIL is already assigned to a non-Super Admin user "
                    "while another Super Admin account exists"
                )
            with get_cursor() as cur:
                cur.execute(
                    """
                    UPDATE config.users
                    SET role = 'SUPER_ADMIN', status = 'ACTIVE', updated_at = NOW()
                    WHERE id = %s
                    """,
                    (rows[0]["id"],),
                )
        return

    if super_admin_rows:
        old_email = super_admin_rows[0]["email"]
        with get_cursor() as cur:
            cur.execute(
                """
                UPDATE config.users
                SET email = %s,
                    status = 'ACTIVE',
                    updated_at = NOW()
                WHERE id = %s
                """,
                (email, super_admin_rows[0]["id"]),
            )
            cur.execute(
                """
                UPDATE config.user_sessions
                SET revoked_at = NOW(), revoked_by = 'system', status = 'REVOKED'
                WHERE user_id = %s AND revoked_at IS NULL
                """,
                (super_admin_rows[0]["id"],),
            )
        audit_event(
            action="super_admin_email_updated",
            entity_type="user",
            entity_id=email,
            actor="system",
            result="SUCCESS",
            details={"old_email": old_email, "new_email": email},
        )
        return

    initial_password = os.getenv("SUPER_ADMIN_INITIAL_PASSWORD", "").strip()
    if not initial_password:
        raise RuntimeError(
            "SUPER_ADMIN_INITIAL_PASSWORD must be set to bootstrap the configured Super Admin account"
        )

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO config.users
                (email, full_name, password_hash, role, status, must_change_password, created_by)
            VALUES (%s, %s, %s, 'SUPER_ADMIN', 'ACTIVE', TRUE, 'system')
            """,
            (email, email.split(".")[0] + " " + email.split(".")[1].split("@")[0], hash_password(initial_password)),
        )
    audit_event(
        action="super_admin_bootstrapped",
        entity_type="user",
        entity_id=email,
        actor="system",
        result="SUCCESS",
        details={"email": email},
    )


def record_login_history(
    email: str,
    status_text: str,
    request: Request,
    user_id: int | None = None,
    failure_reason: str | None = None,
) -> None:
    user_agent = request.headers.get("user-agent")
    browser, os_name = parse_user_agent(user_agent)
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO config.login_history
                (user_id, email, ip_address, user_agent, browser, operating_system, status, failure_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                email.strip().lower(),
                client_ip(request),
                user_agent,
                browser,
                os_name,
                status_text,
                failure_reason,
            ),
        )


def get_user_by_email(email: str) -> dict | None:
    rows = run_query(
        """
        SELECT id, email, full_name, password_hash, role, status, must_change_password
        FROM config.users
        WHERE LOWER(email) = %s AND deleted = FALSE
        """,
        (email.strip().lower(),),
    )
    return rows[0] if rows else None


def require_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    payload = decode_access_token(credentials.credentials)
    rows = run_query(
        """
        SELECT
            u.id,
            u.email,
            u.role,
            u.status,
            u.must_change_password,
            s.id AS session_id,
            s.revoked_at,
            s.expires_at,
            s.status AS session_status
        FROM config.users u
        JOIN config.user_sessions s ON s.user_id = u.id
        WHERE u.id = %s
          AND s.id = %s
          AND s.token_jti = %s
          AND u.deleted = FALSE
        """,
        (int(payload["sub"]), payload["sid"], payload["jti"]),
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session not found")

    row = rows[0]
    if row["status"] != AccountStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
    if row["revoked_at"] is not None or row["session_status"] != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")
    if row["expires_at"] < utcnow():
        with get_cursor() as cur:
            cur.execute("UPDATE config.user_sessions SET status = 'EXPIRED' WHERE id = %s", (row["session_id"],))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired")

    request.state.current_user = AuthenticatedUser(
        id=row["id"],
        email=row["email"],
        role=Role(row["role"]),
        status=AccountStatus(row["status"]),
        must_change_password=bool(row["must_change_password"]),
        session_id=row["session_id"],
    )
    return request.state.current_user


def ensure_password_ready(user: AuthenticatedUser) -> None:
    if user.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password change required")


def require_roles(*roles: Role) -> Callable:
    allowed = set(roles)

    def dependency(user: AuthenticatedUser = Depends(require_current_user)) -> AuthenticatedUser:
        ensure_password_ready(user)
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency


def require_at_least(role: Role) -> Callable:
    minimum = ROLE_RANK[role]

    def dependency(user: AuthenticatedUser = Depends(require_current_user)) -> AuthenticatedUser:
        ensure_password_ready(user)
        if ROLE_RANK[user.role] < minimum:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency
