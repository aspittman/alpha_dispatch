from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[2]


class Location(BaseModel):
    name: str
    state: str = "UT"
    latitude: float
    longitude: float
    radius_miles: float = 30


class OperatingZone(BaseModel):
    name: str
    latitude: float
    longitude: float
    radius_miles: float = 5
    priority: str = "conditional"
    traffic_friction_baseline: int = 0
    directional_drift_risk: int = 0
    user_penalty: int = 0
    parking_difficulty: str = "unknown"
    stopping_access: str = "unknown"
    driving_complexity: str = "unknown"


class TrafficSettings(BaseModel):
    udot_api_key: str | None = None
    udot_base_url: str = "https://www.udottraffic.utah.gov/api/v2"
    udot_enabled: bool = True
    udot_cache_minutes: int = 5
    google_api_key: str | None = None
    google_base_url: str = "https://routes.googleapis.com"
    google_enabled: bool = True
    google_routing_preference: str = "TRAFFIC_AWARE"
    google_cache_minutes: int = 5
    google_max_daily_requests: int = 50
    google_max_destinations_per_check: int = 10
    include_distant_zones_by_default: bool = False
    request_timeout_seconds: float = 10
    planned_shift_end: str | None = None
    drift_penalty_increase_last_90_minutes: bool = True


class AppSettings(BaseModel):
    timezone: str = "America/Denver"
    database_path: str = "data/dispatch.db"
    cache_dir: str = "data/cache"
    report_dir: str = "reports/output"
    manual_events_file: str = "data/manual_events.yaml"
    maximum_driving_distance_miles: float = 45
    preferred_driving_days: list[str] = Field(default_factory=lambda: ["Friday", "Saturday"])
    permitted_start_hour: int | None = None
    permitted_end_hour: int | None = None
    maximum_weekly_hours: float = 20
    maximum_daily_hours: float = 8
    minimum_opportunity_score: float = 35
    minimum_confidence_score: float = 25
    minimum_estimated_attendance: int = 200
    maximum_weather_risk: int = 80
    report_days_ahead: int = 7
    maximum_review_events: int = 5
    maximum_source_age_hours: int = 168
    nearby_radius_miles: float = 3
    nearby_radius_by_venue_type: dict[str, float] = Field(default_factory=lambda: {"stadium": 5, "arena": 3, "theater": 1.5})
    nearby_minimum_attendance: int = 500
    adjacent_window_minutes: int = 30
    email_address: str | None = None


class Settings(BaseModel):
    app: AppSettings
    locations: list[Location]
    venues: dict[str, dict[str, Any]] = Field(default_factory=dict)
    scoring: dict[str, Any] = Field(default_factory=dict)
    holidays: list[dict[str, Any]] = Field(default_factory=list)
    feature_statuses: dict[str, str] = Field(default_factory=dict)
    zones: dict[str, OperatingZone] = Field(default_factory=dict)
    traffic: TrafficSettings = Field(default_factory=TrafficSettings)
    mobility: dict[str, Any] = Field(default_factory=dict)

    def path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else ROOT / path


def _yaml(name: str, default: Any) -> Any:
    path = ROOT / "config" / name
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or default


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    app_data = _yaml("settings.yaml", {})
    if os.getenv("DISPATCH_EMAIL_TO"):
        app_data["email_address"] = os.environ["DISPATCH_EMAIL_TO"]
    traffic = TrafficSettings(
        udot_api_key=os.getenv("UDOT_API_KEY"),
        udot_base_url=os.getenv("UDOT_API_BASE_URL", "https://www.udottraffic.utah.gov/api/v2"),
        udot_enabled=os.getenv("UDOT_ENABLED", "true").lower() == "true",
        udot_cache_minutes=int(os.getenv("UDOT_CACHE_MINUTES", "5")),
        google_api_key=os.getenv("GOOGLE_ROUTES_API_KEY"),
        google_enabled=os.getenv("GOOGLE_ROUTES_ENABLED", "true").lower() == "true",
        google_base_url=os.getenv("GOOGLE_ROUTES_BASE_URL", "https://routes.googleapis.com"),
        google_routing_preference=os.getenv("GOOGLE_ROUTES_ROUTING_PREFERENCE", "TRAFFIC_AWARE"),
        google_cache_minutes=int(os.getenv("GOOGLE_ROUTES_CACHE_MINUTES", "5")),
        google_max_daily_requests=int(os.getenv("GOOGLE_ROUTES_MAX_DAILY_REQUESTS", "50")),
        google_max_destinations_per_check=int(os.getenv("GOOGLE_ROUTES_MAX_DESTINATIONS_PER_CHECK", "10")),
        include_distant_zones_by_default=os.getenv("INCLUDE_DISTANT_ZONES_BY_DEFAULT", "false").lower() == "true",
        planned_shift_end=os.getenv("PLANNED_SHIFT_END"),
        drift_penalty_increase_last_90_minutes=os.getenv("DRIFT_PENALTY_INCREASE_LAST_90_MINUTES", "true").lower() == "true",
    )
    zone_data = _yaml("operating_zones.yaml", {})
    return Settings(
        app=AppSettings.model_validate(app_data),
        locations=[Location.model_validate(item) for item in _yaml("locations.yaml", [])],
        venues=_yaml("venues.yaml", {}),
        scoring=_yaml("scoring.yaml", {}),
        holidays=_yaml("holidays.yaml", []),
        feature_statuses=_yaml("feature_statuses.yaml", {}),
        zones={key: OperatingZone(name=key, **value) for key, value in zone_data.get("zones", {}).items()},
        traffic=traffic,
        mobility=zone_data,
    )
