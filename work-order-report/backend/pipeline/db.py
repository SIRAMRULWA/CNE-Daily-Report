"""
pipeline/db.py
==============
PostgreSQL connection manager.

Responsibilities:
  - Build connection string from DATABASE_URL or individual DB_* env vars.
  - Provide get_cursor() context manager for transactional psycopg2 operations.
  - Provide run_query() returning list[dict] for API read paths.
  - Provide test_connection(), execute_sql_file() helpers.
  - Inject SSL settings when global-bundle.pem is present at project root.

SSL:
  Place the AWS RDS global-bundle.pem at the project root and the engine
  will automatically use sslmode=verify-full.
"""

import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

_CERT_PATH = Path(__file__).parent.parent / "global-bundle.pem"


def _build_dsn() -> str:
    """
    Construct a libpq connection string.
    DATABASE_URL takes precedence over individual DB_* variables.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host     = os.getenv("DB_HOST", "localhost")
    port     = os.getenv("DB_PORT", "5432")
    name     = os.getenv("DB_NAME", "wo_reports")
    user     = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def _ssl_args() -> dict:
    if _CERT_PATH.exists():
        return {"sslmode": "verify-full", "sslrootcert": str(_CERT_PATH)}
    return {}


def _connect_args() -> dict:
    args = _ssl_args()
    timeout = os.getenv("DB_CONNECT_TIMEOUT", "5").strip()
    if timeout:
        args["connect_timeout"] = int(timeout)
    return args


def _retry_settings() -> tuple[int, float]:
    attempts = int(os.getenv("DB_CONNECT_RETRIES", "3"))
    delay = float(os.getenv("DB_RETRY_DELAY_SECONDS", "2"))
    return max(attempts, 1), max(delay, 0)


def _connect():
    """Open a psycopg2 connection with retries for transient DNS/network failures."""
    dsn = _build_dsn()
    attempts, delay = _retry_settings()
    last_exc = None

    for attempt in range(1, attempts + 1):
        try:
            return psycopg2.connect(dsn, **_connect_args())
        except psycopg2.OperationalError as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            logger.warning(
                "Database connection attempt %d/%d failed: %s. Retrying in %.1fs",
                attempt,
                attempts,
                exc,
                delay,
            )
            if delay:
                time.sleep(delay)

    raise last_exc


def get_engine():
    """Return a SQLAlchemy engine. Used by dbt-compatible helpers and pandas."""
    dsn = _build_dsn()
    return create_engine(dsn, connect_args=_connect_args())


@contextmanager
def get_cursor():
    """
    Context manager for a transactional psycopg2 cursor.
    Commits on success, rolls back on exception, always closes the connection.

    Usage:
        with get_cursor() as cur:
            cur.execute("INSERT INTO ...")
    """
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_query(sql: str, params: tuple | dict | None = None) -> list[dict]:
    """
    Execute a read query and return results as list[dict].
    Used by all API endpoint handlers.
    """
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def test_connection() -> bool:
    """
    Verify the database is reachable.
    Returns True on success, raises on failure.
    """
    try:
        rows = run_query("SELECT 1 AS ok")
        assert rows[0]["ok"] == 1
        logger.info("Database connection OK")
        return True
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)
        raise


def execute_sql_file(filepath: str | Path) -> None:
    """
    Execute a multi-statement SQL file (e.g. schema migrations).
    """
    filepath = Path(filepath)
    sql = filepath.read_text(encoding="utf-8")
    with get_cursor() as cur:
        cur.execute(sql)
    logger.info("Executed SQL file: %s", filepath.name)
