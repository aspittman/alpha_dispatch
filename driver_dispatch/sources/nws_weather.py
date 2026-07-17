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
            alerts_data = self.get_json("https://api.weather.gov/alerts/active", {"point": f"{latitude:.4f},{longitude:.4f}"}, self.headers)
            alerts = [feature.get("properties", {}).get("headline") for feature in alerts_data.get("features", []) if feature.get("properties", {}).get("headline")]
            risk = weather_risk(text, p.get("windSpeed", ""))
            return {"temperature": p.get("temperature"), "temperature_unit": p.get("temperatureUnit"), "wind_speed": p.get("windSpeed"), "short_forecast": text, "precipitation_probability": (p.get("probabilityOfPrecipitation") or {}).get("value"), "risk": risk, "severe_alerts": alerts, "snow_ice_risk": any(word in text.lower() for word in ("snow", "ice", "freezing")), "outdoor_cancellation_risk": "high" if risk >= 75 else "moderate" if risk >= 50 else "low", "forecast_generated_at": forecast.get("properties", {}).get("generatedAt"), "source": "National Weather Service"}
        except (KeyError, ValueError, SourceError) as exc:
            raise SourceError(f"NWS forecast unavailable: {exc}") from exc


def weather_risk(text: str, wind: str = "") -> int:
    value = text.lower()
    if any(word in value for word in ("blizzard", "ice storm", "severe thunderstorm", "tornado")): return 95
    if any(word in value for word in ("heavy snow", "freezing rain", "thunderstorm")): return 75
    if any(word in value for word in ("snow", "heavy rain")): return 55
    if any(word in value for word in ("rain", "showers")): return 25
    return 5
