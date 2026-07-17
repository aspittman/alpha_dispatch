from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from driver_dispatch.models import TrafficIncident
from driver_dispatch.traffic_cache import JsonCache

log = logging.getLogger(__name__)


def _time(value):
    if value in (None, ""): return None
    if isinstance(value, (int, float)):
        if value > 10_000_000_000: value /= 1000
        return datetime.fromtimestamp(value, timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try: return datetime.fromisoformat(text)
    except ValueError: return None


def _category(record: dict[str, Any]) -> str:
    text = " ".join(str(record.get(k, "")) for k in ("EventType", "Type", "Description", "Headline")).lower()
    for needle, category in (("construction", "construction"), ("crash", "crash"), ("accident", "crash"), ("closed", "closure"), ("closure", "closure"), ("lane", "lane_restriction"), ("disabled", "disabled_vehicle"), ("weather", "weather"), ("road condition", "road_condition"), ("special event", "special_event")):
        if needle in text: return category
    return "other"


def normalize_udot(record: dict[str, Any], kind: str = "event") -> TrafficIncident:
    description = str(record.get("Description") or record.get("Headline") or record.get("Message") or "UDOT condition")
    category = _category(record)
    planned = category == "construction" or bool(record.get("IsPlanned") or record.get("Planned"))
    return TrafficIncident(
        source_id=str(record.get("Id") or record.get("ID") or record.get("EventId") or record.get("AlertId") or description[:80]),
        category=category, roadway_name=record.get("RoadwayName") or record.get("RoadName") or record.get("Roadway"),
        direction=record.get("DirectionOfTravel") or record.get("Direction"), description=description,
        severity=str(record.get("Severity") or record.get("Priority") or "unknown").lower(),
        latitude=record.get("Latitude") or record.get("Lat"), longitude=record.get("Longitude") or record.get("Lng"),
        start_time=_time(record.get("StartDate") or record.get("StartTime")), end_time=_time(record.get("EndDate") or record.get("EndTime")),
        reported_time=_time(record.get("Reported") or record.get("Created")), last_updated=_time(record.get("LastUpdated") or record.get("Updated")),
        active=not bool(record.get("IsInactive", False)), planned=planned,
        raw_source_reference={"kind": kind, "record": record},
    )


class UdotTrafficAdapter:
    """Official UDOT Traffic v2 REST client. Developer key is always a query parameter."""
    _lock = threading.Lock()
    _calls: list[float] = []

    def __init__(self, settings, cache: JsonCache, client=None, sleep=time.sleep, ledger=None):
        self.settings, self.cache = settings, cache
        self.client = client or httpx.Client(timeout=settings.request_timeout_seconds)
        self.ledger = ledger
        self.sleep = sleep
        self.stats = {"api_calls": 0, "cache_hits": 0}

    def _throttle(self):
        with self._lock:
            now = time.monotonic(); self._calls[:] = [t for t in self._calls if now - t < 60]
            if len(self._calls) >= self.settings.udot_max_calls_per_minute:
                self.sleep(max(0, 60 - (now - self._calls[0])))
            self._calls.append(time.monotonic())

    def _get(self, endpoint: str):
        key = endpoint
        cached = self.cache.get("udot", key, self.settings.udot_cache_minutes)
        if cached:
            self.stats["cache_hits"] += 1; log.info("udot_cache_hit", extra={"endpoint": endpoint}); return cached[0]
        if not self.settings.udot_enabled or not self.settings.udot_api_key: raise RuntimeError("UDOT Traffic is disabled or UDOT_API_KEY is not configured")
        error = None
        for attempt in range(3):
            try:
                self._throttle(); self.stats["api_calls"] += 1
                response = self.client.get(f"{self.settings.udot_base_url.rstrip('/')}/{endpoint.lstrip('/')}", params={"key": self.settings.udot_api_key})
                response.raise_for_status(); data = response.json()
                if not isinstance(data, (list, dict)): raise ValueError("UDOT response must be a list or object")
                if self.ledger: self.ledger.record_udot()
                self.cache.set("udot", key, data); return data
            except (httpx.HTTPError, ValueError) as exc:
                error = exc
                if attempt < 2: self.sleep(2 ** attempt)
        raise RuntimeError(f"UDOT request failed: {type(error).__name__}") from error

    def incidents(self) -> list[TrafficIncident]:
        output = []
        endpoints = (("get/event", "event"), ("get/alert", "alert"))[:self.settings.udot_max_calls_per_refresh]
        for endpoint, kind in endpoints:
            data = self._get(endpoint)
            records = data if isinstance(data, list) else data.get("items") or data.get("Events") or data.get("Alerts") or []
            output.extend(normalize_udot(item, kind) for item in records if isinstance(item, dict))
        return output
