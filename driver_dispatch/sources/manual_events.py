from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from driver_dispatch.models import Event
from .base import EventSource


class ManualEventSource(EventSource):
    name = "manual"

    def __init__(self, path: Path):
        self.path = path

    def collect(self, start: datetime, end: datetime) -> list[Event]:
        if not self.path.exists():
            return []
        data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        events = []
        for index, item in enumerate(data.get("events", [])):
            event = Event.model_validate({"source": self.name, "source_event_id": item.get("id", f"manual-{index}"), **item})
            if event.start_datetime and start <= event.start_datetime < end:
                events.append(event)
        return events

