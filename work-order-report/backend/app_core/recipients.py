"""Shared email-address and recipient-domain policy."""

from __future__ import annotations

import os
import re

from app_core.settings import env_flag

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
DEFAULT_ALLOWED_DOMAINS = frozenset(
    {"vodacom.co.za", "vodacom.com", "vcontractor.co.za"}
)


class RecipientPolicyError(ValueError):
    pass


def normalize_addresses(values: list[str]) -> list[str]:
    cleaned = list(
        dict.fromkeys(
            value.strip().lower() for value in values if value and value.strip()
        )
    )
    if any(not EMAIL_RE.match(value) for value in cleaned):
        raise RecipientPolicyError("Every recipient must be a valid email address")
    return cleaned


def validate_recipient_domains(addresses: list[str]) -> None:
    if env_flag("REPORT_EMAIL_ALLOW_EXTERNAL", False):
        return
    configured = os.getenv("REPORT_EMAIL_ALLOWED_DOMAINS") or os.getenv(
        "AUTH_ALLOWED_EMAIL_DOMAINS", ""
    )
    allowed = {
        item.strip().lower() for item in configured.split(",") if item.strip()
    } or DEFAULT_ALLOWED_DOMAINS
    rejected = [
        address for address in addresses
        if address.rsplit("@", 1)[-1].lower() not in allowed
    ]
    if rejected:
        raise RecipientPolicyError(
            f"Recipients outside approved domains: {', '.join(rejected)}"
        )
