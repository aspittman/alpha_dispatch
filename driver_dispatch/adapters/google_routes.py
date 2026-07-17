from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from driver_dispatch.models import RouteMetric
from driver_dispatch.api_usage import UsageLedger, UsageLimitExceeded, matrix_elements
from driver_dispatch.traffic_cache import JsonCache

log = logging.getLogger(__name__)
FIELD_MASK = "originIndex,destinationIndex,status,condition,distanceMeters,duration,staticDuration"


class GoogleQuotaExceeded(UsageLimitExceeded): pass


def duration_seconds(value) -> float | None:
    if value is None: return None
    if isinstance(value, (int, float)): return float(value)
    text = str(value)
    if text.endswith("s"):
        try: return float(text[:-1])
        except ValueError: return None
    return None


def severity(delay: float | None, multiplier: float | None, thresholds: dict) -> str:
    if delay is None or multiplier is None: return "unavailable"
    levels = ["clear", "minor", "moderate", "heavy"]
    delay_level = multiplier_level = 4
    for i, level in enumerate(levels):
        rule = thresholds[level]
        if delay <= rule["maximum_delay_minutes"]: delay_level = i; break
    for i, level in enumerate(levels):
        if multiplier <= thresholds[level]["maximum_multiplier"]: multiplier_level = i; break
    index = max(delay_level, multiplier_level)
    return levels[index] if index < 4 else "severe"


class GoogleRoutesAdapter:
    def __init__(self, settings, cache: JsonCache, thresholds: dict, client=None, ledger: UsageLedger | None = None):
        self.settings, self.cache, self.thresholds = settings, cache, thresholds
        self.ledger = ledger
        if ledger is None: raise ValueError("GoogleRoutesAdapter requires a persistent UsageLedger")
        self.client = client or httpx.Client(timeout=settings.request_timeout_seconds)
        self.stats = {"api_calls": 0, "cache_hits": 0, "elements": 0}
    @property
    def remaining(self):
        usage = self.ledger.usage(); limit = usage["google_daily_limit"]
        return max(0, limit - usage["google_today"]) if limit is not None else None

    def matrix(self, origin: tuple[float, float], destinations: list[tuple[str, float, float]], mode="pre_shift", force=False, confirmed=False, run_id=None):
        if mode == "weekly": raise GoogleQuotaExceeded("weekly mode does not make live Google traffic requests")
        if len(destinations) > self.settings.google_max_elements_per_refresh: destinations = destinations[:self.settings.google_max_elements_per_refresh]
        now = datetime.now(timezone.utc); minutes = max(5 if self.settings.low_usage_mode else 1, self.settings.google_cache_minutes)
        bucket = now.replace(minute=(now.minute // minutes) * minutes, second=0, microsecond=0).isoformat()
        rounded = tuple(round(x, self.settings.google_origin_rounding_decimals) for x in origin)
        key = {"origin_zone": rounded, "destinations": [(n, round(a,4), round(b,4)) for n,a,b in destinations], "travel_mode":"DRIVE", "preference": self.settings.google_routing_preference, "departure_bucket": bucket, "mode": mode}
        cache_age = max(5, self.settings.google_cache_minutes) if self.settings.low_usage_mode else self.settings.google_cache_minutes
        cached = self.cache.get("google-matrix", key, cache_age)
        if cached and not force:
            self.stats["cache_hits"] += len(destinations); return self._parse(cached[0], destinations, origin, cached[1], True)
        if force:
            if not self.settings.google_allow_force_refresh: raise GoogleQuotaExceeded("force refresh is disabled")
            if cached and not confirmed: raise GoogleQuotaExceeded(f"fresh cached result exists; confirm force refresh of {matrix_elements(1, len(destinations))} elements")
            recent = self.cache.get("google-force-refresh", rounded, self.settings.google_force_refresh_cooldown_minutes)
            if recent: raise GoogleQuotaExceeded("force-refresh cooldown is active")
        if not self.settings.google_enabled or not self.settings.google_api_key: raise RuntimeError("Google Routes is disabled or GOOGLE_ROUTES_API_KEY is not configured")
        try: reservation = self.ledger.reserve_google(1, len(destinations), run_id=run_id)
        except UsageLimitExceeded as exc: raise GoogleQuotaExceeded(str(exc)) from exc
        body = {"origins": [{"waypoint": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}}}], "destinations": [{"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lon}}}} for _, lat, lon in destinations], "travelMode": "DRIVE", "routingPreference": self.settings.google_routing_preference}
        headers = {"X-Goog-Api-Key": self.settings.google_api_key, "X-Goog-FieldMask": FIELD_MASK, "Content-Type": "application/json"}
        self.stats["api_calls"] += 1; self.stats["elements"] += len(destinations)
        try:
            response = self.client.post(f"{self.settings.google_base_url.rstrip('/')}/distanceMatrix/v2:computeRouteMatrix", json=body, headers=headers)
            response.raise_for_status(); data = response.json()
            if not isinstance(data, list): raise ValueError("Google route matrix response must be a list")
        except Exception as exc:
            # Once dispatch is attempted, acceptance is ambiguous. Count conservatively.
            self.ledger.finish(reservation, "failed_unknown_billing", type(exc).__name__)
            raise
        self.ledger.finish(reservation)
        self.cache.set("google-matrix", key, data)
        if force: self.cache.set("google-force-refresh", rounded, {"request_id":reservation.request_id})
        return self._parse(data, destinations, origin, 0, False)

    def _parse(self, rows, destinations, origin, age, cache_hit):
        output = {}
        for row in rows:
            index = row.get("destinationIndex", 0)
            if index >= len(destinations) or row.get("condition") not in (None, "ROUTE_EXISTS"): continue
            name = destinations[index][0]; live = duration_seconds(row.get("duration")); static = duration_seconds(row.get("staticDuration")); meters = row.get("distanceMeters")
            live_m = live / 60 if live is not None else None; static_m = static / 60 if static is not None else None
            delay = max(0, live_m - static_m) if live_m is not None and static_m is not None else None
            mult = live_m / static_m if live_m is not None and static_m and static_m > 0 else None
            miles = meters / 1609.344 if meters is not None else None
            output[name] = RouteMetric(origin_name="current", destination_name=name, live_duration_minutes=live_m, static_duration_minutes=static_m, delay_minutes=delay, delay_percentage=(mult - 1) * 100 if mult is not None else None, traffic_multiplier=mult, distance_miles=miles, average_route_speed=miles / (live_m / 60) if miles is not None and live_m else None, data_age_minutes=age, traffic_severity=severity(delay, mult, self.thresholds), fetched_at=datetime.now(timezone.utc), cache_hit=cache_hit)
        return output
