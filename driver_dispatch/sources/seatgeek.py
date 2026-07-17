from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from driver_dispatch.models import Event
from .base import HttpEventSource, SourceError


class SeatGeekSource(HttpEventSource):
    name = "seatgeek"
    url = "https://api.seatgeek.com/2/events"

    def __init__(self, cache_dir: Path, locations: list, client_id: str | None = None):
        super().__init__(cache_dir)
        self.locations = locations
        self.client_id = client_id or os.getenv("SEATGEEK_CLIENT_ID")

    def collect(self, start: datetime, end: datetime) -> list[Event]:
        if not self.client_id:
            raise SourceError("SEATGEEK_CLIENT_ID is not configured")
        events = []
        for location in self.locations:
            params = {"client_id": self.client_id, "lat": location.latitude, "lon": location.longitude, "range": f"{int(location.radius_miles)}mi", "datetime_utc.gte": start.isoformat(), "datetime_utc.lt": end.isoformat(), "per_page": 200}
            for item in self.get_json(self.url, params).get("events", []):
                venue = item.get("venue") or {}
                taxonomy = " ".join(t.get("name", "") for t in item.get("taxonomies", [])).lower()
                events.append(Event(source=self.name, source_event_id=str(item.get("id")), name=item.get("title") or "Unknown event", event_type=self._type(taxonomy), venue_name=venue.get("name"), venue_address=venue.get("address"), city=venue.get("city"), state=venue.get("state"), latitude=(venue.get("location") or {}).get("lat"), longitude=(venue.get("location") or {}).get("lon"), start_datetime=self._utc_datetime(item.get("datetime_utc")), venue_capacity=venue.get("capacity"), ticket_status="available" if item.get("stats", {}).get("listing_count") else None, event_url=item.get("url"), raw_source_data=item))
        return events

    @staticmethod
    def _utc_datetime(value):
        if not value: return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)

    @staticmethod
    def _type(text):
        if "concert" in text: return "concert"
        if "sports" in text: return "professional_sports"
        if "theater" in text: return "theater"
        if "comedy" in text: return "comedy"
        return "other"
