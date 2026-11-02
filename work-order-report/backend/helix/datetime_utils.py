"""Helix timestamp parsing and AR qualification formatting."""

from datetime import date, datetime, time as datetime_time
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from helix.config import WORKSPACE_TIMEZONE


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

