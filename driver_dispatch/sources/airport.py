"""Future airport integration boundary; intentionally inactive in V1."""
from .base import EventSource


class AirportSource(EventSource):
    name = "airport_placeholder"

    def collect(self, start, end):
        return []

