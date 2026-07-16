from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from driver_dispatch.models import Event


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
    zone = ZoneInfo(event.timezone or timezone_name)
    for field in ("start_datetime", "end_datetime", "estimated_end_datetime"):
        value: datetime | None = getattr(event, field)
        if value and value.tzinfo is None:
            setattr(event, field, value.replace(tzinfo=zone))
        elif value:
            setattr(event, field, value.astimezone(zone))
    event.timezone = str(zone)
    event.source_attributions = sorted(set(event.source_attributions + [event.source]))
    return event
