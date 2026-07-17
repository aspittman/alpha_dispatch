from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "America/Denver"


def local_datetime(value: datetime, timezone_name: str = DEFAULT_TIMEZONE) -> datetime:
    """Return an aware market-local datetime; naive input is interpreted as source local time."""
    zone = ZoneInfo(timezone_name)
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone)
    return value.astimezone(zone)


def timezone_label(value: datetime | None) -> str:
    return value.tzname() if value and value.tzinfo else ""
