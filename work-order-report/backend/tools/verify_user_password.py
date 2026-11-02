"""
Verify whether a candidate password matches a stored user hash.

Usage:
    python tools/verify_user_password.py user@example.com

The script prompts for the password and prints only MATCH/NO_MATCH metadata.
It does not modify the database and does not print the stored hash.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.auth import verify_password  # noqa: E402
from pipeline.db import run_query  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/verify_user_password.py user@example.com")
        return 2

    email = sys.argv[1].strip().lower()
    password = getpass.getpass("Candidate password: ").strip()

    rows = run_query(
        """
        SELECT id, email, status, must_change_password, password_hash
        FROM config.users
        WHERE LOWER(email) = %s AND deleted = FALSE
        """,
        (email,),
    )

    if not rows:
        print(f"USER_NOT_FOUND email={email}")
        return 1

    user = rows[0]
    matches = verify_password(password, user["password_hash"])
    result = "MATCH" if matches else "NO_MATCH"
    print(
        f"{result} email={user['email']} "
        f"status={user['status']} "
        f"must_change_password={user['must_change_password']}"
    )
    return 0 if matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
