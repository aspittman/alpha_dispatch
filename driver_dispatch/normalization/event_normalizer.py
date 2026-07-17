from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from driver_dispatch.models import Event
from .timezones import local_datetime


def normalized_text(value: str | None) -> str:
    if not value:
        return ""
    value = "".join(character if character.isalnum() else " " for character in value)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"\b(the|live|presented by)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def normalize_event(event: Event, timezone_name: str = "America/Denver") -> Event:
    event.name = " ".join(event.name.split())
    event.city = " ".join(event.city.split()).title() if event.city else None
    event.state = event.state.upper() if event.state else None
    zone = ZoneInfo(timezone_name)
    for field in ("start_datetime", "end_datetime", "estimated_end_datetime"):
        value: datetime | None = getattr(event, field)
        if value:
            setattr(event, field, local_datetime(value, timezone_name))
    event.timezone = str(zone)
    event.source_attributions = sorted(set(event.source_attributions + [event.source]))
    if event.source_event_id:
        event.source_event_ids.setdefault(event.source, [])
        event.source_event_ids[event.source] = sorted(set(event.source_event_ids[event.source] + [event.source_event_id]))
    if event.event_url:
        event.source_urls = sorted(set(event.source_urls + [event.event_url]))
    event.fetched_at = event.fetched_at or datetime.now(timezone.utc)
    event.normalized_at = datetime.now(timezone.utc)
    event.source_values.setdefault(event.source, {})
    for field in ("name", "start_datetime", "venue_name", "venue_address", "city", "latitude", "longitude", "estimated_attendance"):
        value = getattr(event, field)
        if value is not None:
            event.source_values[event.source][field] = value.isoformat() if isinstance(value, datetime) else value
    return event
