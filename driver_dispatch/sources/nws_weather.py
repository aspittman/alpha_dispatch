from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .base import HttpEventSource, SourceError


class NWSWeatherSource(HttpEventSource):
    name = "nws"

    def __init__(self, cache_dir: Path):
        super().__init__(cache_dir, cache_ttl=3600)
        self.headers = {"User-Agent": os.getenv("NWS_USER_AGENT", "DriverDispatchIntelligence/1.0 (personal-use)")}

    def collect(self, start: datetime, end: datetime):
        return []

    def forecast(self, latitude: float, longitude: float, at: datetime) -> dict | None:
        try:
            point = self.get_json(f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}", {}, self.headers)
            url = point["properties"]["forecastHourly"]
            forecast = self.get_json(url, {}, self.headers)
            periods = forecast.get("properties", {}).get("periods", [])
            matching = [p for p in periods if datetime.fromisoformat(p["startTime"]) <= at < datetime.fromisoformat(p["endTime"])]
            if not matching:
                return None
            p = matching[0]
            text = p.get("shortForecast", "")
            return {"temperature": p.get("temperature"), "temperature_unit": p.get("temperatureUnit"), "wind_speed": p.get("windSpeed"), "short_forecast": text, "precipitation_probability": (p.get("probabilityOfPrecipitation") or {}).get("value"), "risk": weather_risk(text, p.get("windSpeed", ""))}
        except (KeyError, ValueError, SourceError) as exc:
            raise SourceError(f"NWS forecast unavailable: {exc}") from exc


def weather_risk(text: str, wind: str = "") -> int:
    value = text.lower()
    if any(word in value for word in ("blizzard", "ice storm", "severe thunderstorm", "tornado")): return 95
    if any(word in value for word in ("heavy snow", "freezing rain", "thunderstorm")): return 75
    if any(word in value for word in ("snow", "heavy rain")): return 55
    if any(word in value for word in ("rain", "showers")): return 25
    return 5

