"""Safe extension point for official JSON/RSS/iCal calendars.

Adapters should use a documented feed or permitted low-frequency access. HTML
anti-bot controls and authentication are deliberately not circumvented.
"""
from driver_dispatch.sources.base import EventSource


class FeedCalendarSource(EventSource):
    name = "official_calendar_placeholder"

    def __init__(self, config: dict):
        self.config = config

    def collect(self, start, end):
        return []

