from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from driver_dispatch.models import Event
from .base import HttpEventSource, SourceError


class TicketmasterSource(HttpEventSource):
    name = "ticketmaster"
    url = "https://app.ticketmaster.com/discovery/v2/events.json"

    def __init__(self, cache_dir: Path, locations: list, api_key: str | None = None):
        super().__init__(cache_dir)
        self.locations = locations
        self.api_key = api_key or os.getenv("TICKETMASTER_API_KEY")

    def collect(self, start: datetime, end: datetime) -> list[Event]:
        if not self.api_key:
            raise SourceError("TICKETMASTER_API_KEY is not configured")
        events: list[Event] = []
        for location in self.locations:
            params = {"apikey": self.api_key, "latlong": f"{location.latitude},{location.longitude}", "radius": int(location.radius_miles), "unit": "miles", "startDateTime": self._api_datetime(start), "endDateTime": self._api_datetime(end), "size": 200, "sort": "date,asc"}
            for item in self.get_json(self.url, params).get("_embedded", {}).get("events", []):
                venue = (item.get("_embedded", {}).get("venues") or [{}])[0]
                dates = item.get("dates", {})
                events.append(Event(source=self.name, source_event_id=item.get("id"), name=item.get("name") or "Unknown event", event_type=self._type(item), venue_name=venue.get("name"), venue_address=(venue.get("address") or {}).get("line1"), city=(venue.get("city") or {}).get("name"), state=(venue.get("state") or {}).get("stateCode"), latitude=self._float((venue.get("location") or {}).get("latitude")), longitude=self._float((venue.get("location") or {}).get("longitude")), start_datetime=dates.get("start", {}).get("dateTime"), ticket_status=(dates.get("status") or {}).get("code"), event_url=item.get("url"), status="canceled" if (dates.get("status") or {}).get("code") == "cancelled" else "scheduled", raw_source_data=item))
        return events

    @staticmethod
    def _api_datetime(value: datetime) -> str:
        """Format datetimes as the UTC value required by Ticketmaster."""
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _float(value):
        return float(value) if value is not None else None

    @staticmethod
    def _type(item):
        text = " ".join(c.get("segment", {}).get("name", "") + " " + c.get("genre", {}).get("name", "") for c in item.get("classifications", [])).lower()
        if "music" in text: return "concert"
        if "sports" in text: return "professional_sports"
        if "comedy" in text: return "comedy"
        if "theatre" in text or "arts" in text: return "theater"
        return "other"
