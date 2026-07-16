from __future__ import annotations

from datetime import datetime

from driver_dispatch.models import Event
from .base import EventSource


class HolidaySource(EventSource):
    name = "static_holidays"

    def __init__(self, holidays: list[dict], timezone):
        self.holidays = holidays
        self.timezone = timezone

    def collect(self, start: datetime, end: datetime) -> list[Event]:
        result = []
        for year in range(start.year, end.year + 1):
            for item in self.holidays:
                at = datetime(year, item["month"], item["day"], 18, tzinfo=self.timezone)
                if start <= at < end:
                    result.append(Event(source=self.name, source_event_id=f'{year}-{item["month"]}-{item["day"]}', name=item["name"], event_type=item.get("event_type", "holiday_celebration"), city=None, start_datetime=at, estimated_attendance=item.get("estimated_attendance"), attendance_confidence=0.2, raw_source_data=item))
        return result

