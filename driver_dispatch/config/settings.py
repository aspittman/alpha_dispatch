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


class AppSettings(BaseModel):
    timezone: str = "America/Denver"
    database_path: str = "data/dispatch.db"
    cache_dir: str = "data/cache"
    report_dir: str = "reports/output"
    manual_events_file: str = "data/manual_events.yaml"
    maximum_driving_distance_miles: float = 45
    preferred_driving_days: list[str] = Field(default_factory=lambda: ["Friday", "Saturday"])
    permitted_start_hour: int = 5
    permitted_end_hour: int = 2
    maximum_weekly_hours: float = 20
    minimum_opportunity_score: float = 35
    minimum_confidence_score: float = 25
    minimum_estimated_attendance: int = 200
    maximum_weather_risk: int = 80
    report_days_ahead: int = 7
    email_address: str | None = None


class Settings(BaseModel):
    app: AppSettings
    locations: list[Location]
    venues: dict[str, dict[str, Any]] = Field(default_factory=dict)
    scoring: dict[str, Any] = Field(default_factory=dict)
    holidays: list[dict[str, Any]] = Field(default_factory=list)

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
    return Settings(
        app=AppSettings.model_validate(app_data),
        locations=[Location.model_validate(item) for item in _yaml("locations.yaml", [])],
        venues=_yaml("venues.yaml", {}),
        scoring=_yaml("scoring.yaml", {}),
        holidays=_yaml("holidays.yaml", []),
    )

