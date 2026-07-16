"""Future traffic integration boundary; intentionally inactive in V1."""
from .base import EventSource


class TrafficSource(EventSource):
    name = "traffic_placeholder"

    def collect(self, start, end):
        return []
