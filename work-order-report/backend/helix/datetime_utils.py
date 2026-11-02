"""Helix timestamp parsing and AR qualification formatting."""

from datetime import date, datetime, time as datetime_time
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from config.mappings import DATE_ONLY_END_OF_DAY
from helix.config import WORKSPACE_TIMEZONE

_DATE_ONLY_LENGTH = len("YYYY-MM-DD")


def naive_workspace_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo(WORKSPACE_TIMEZONE)).replace(tzinfo=None)


def parse_helix_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return naive_workspace_datetime(value)
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 9_999_999_999 else value
        return datetime.fromtimestamp(
            timestamp, tz=ZoneInfo(WORKSPACE_TIMEZONE)
        ).replace(tzinfo=None)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        numeric = float(raw)
        timestamp = numeric / 1000 if numeric > 9_999_999_999 else numeric
        return datetime.fromtimestamp(
            timestamp, tz=ZoneInfo(WORKSPACE_TIMEZONE)
        ).replace(tzinfo=None)
    except (ValueError, TypeError, OSError):
        pass
    try:
        return naive_workspace_datetime(date_parser.parse(raw))
    except (ValueError, TypeError, OverflowError):
        return None


def format_helix_timestamp(
    value: datetime | date | str, end_of_day: bool = False
) -> str:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        boundary = datetime_time.max if end_of_day else datetime_time.min
        dt = datetime.combine(value, boundary).replace(microsecond=0)
    else:
        raw = value.strip()
        try:
            parsed = date_parser.parse(raw)
        except (ValueError, TypeError, OverflowError):
            return raw
        is_date_only = len(raw) <= 10 and parsed.time() == datetime_time.min
        if end_of_day and is_date_only:
            parsed = datetime.combine(
                parsed.date(), datetime_time.max
            ).replace(microsecond=0)
        dt = parsed
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(WORKSPACE_TIMEZONE))
    return str(int(dt.timestamp()))



def is_date_only(value) -> bool:
    """True when a source value carries a calendar date but no time of day."""
    if isinstance(value, datetime):
        return False
    if isinstance(value, date):
        return True
    raw = str(value or "").strip()
    # Epoch values (all digits) carry a time; only dashed/slashed dates qualify.
    if not raw or len(raw) > _DATE_ONLY_LENGTH or not any(c in raw for c in "-/"):
        return False
    try:
        date_parser.parse(raw)
    except (ValueError, TypeError, OverflowError):
        return False
    return True


def end_of_day(value: datetime) -> datetime:
    return datetime.combine(value.date(), datetime_time(23, 59, 59))


def parse_target_date(value) -> datetime | None:
    """Parse a Work Order target date.

    A date with no time of day is due at the end of that day (23:59:59 local),
    so a Work Order is not shown as late from midnight on its own due date.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime_time.min)
        return end_of_day(value) if DATE_ONLY_END_OF_DAY else value
    parsed = parse_helix_datetime(value)
    if parsed is not None and DATE_ONLY_END_OF_DAY and is_date_only(value):
        return end_of_day(parsed)
    return parsed
