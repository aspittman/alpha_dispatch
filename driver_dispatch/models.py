from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from zoneinfo import ZoneInfo


class EventType(str, Enum):
    CONCERT = "concert"
    PROFESSIONAL_SPORTS = "professional_sports"
    COLLEGE_SPORTS = "college_sports"
    CONVENTION = "convention"
    TRADE_SHOW = "trade_show"
    FESTIVAL = "festival"
    FAIR = "fair"
    THEATER = "theater"
    COMEDY = "comedy"
    GRADUATION = "graduation"
    UNIVERSITY_EVENT = "university_event"
    RELIGIOUS_EVENT = "religious_event"
    PARADE = "parade"
    HOLIDAY_CELEBRATION = "holiday_celebration"
    NIGHTLIFE = "nightlife"
    AIRPORT_TRAVEL = "airport_travel"
    OTHER = "other"


class FeatureStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    NOT_CONFIGURED = "not_configured"
    SOURCE_FAILED = "source_failed"
    NO_DATA_FOUND = "no_data_found"
    DATA_STALE = "data_stale"
    AVAILABLE = "available"


class Event(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    id: str | None = None
    source: str
    source_event_id: str | None = None
    source_attributions: list[str] = Field(default_factory=list)
    source_event_ids: dict[str, list[str]] = Field(default_factory=dict)
    source_urls: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None
    source_last_updated_at: datetime | None = None
    normalized_at: datetime | None = None
    name: str
    event_type: EventType = EventType.OTHER
    venue_name: str | None = None
    venue_address: str | None = None
    city: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    estimated_end_datetime: datetime | None = None
    timezone: str = "America/Denver"
    venue_capacity: int | None = None
    estimated_attendance: int | None = None
    estimated_attendance_low: int | None = None
    estimated_attendance_high: int | None = None
    estimated_attendance_midpoint: int | None = None
    attendance_basis: str = "unknown"
    attendance_confidence: float | None = None
    ticket_status: str | None = None
    outdoor_event: bool | None = None
    event_url: str | None = None
    date_first_seen: datetime | None = None
    date_last_updated: datetime | None = None
    status: str = "scheduled"
    raw_source_data: dict[str, Any] = Field(default_factory=dict)
    source_values: dict[str, dict[str, Any]] = Field(default_factory=dict)
    conflicting_fields: dict[str, list[Any]] = Field(default_factory=dict)
    selected_values: dict[str, Any] = Field(default_factory=dict)
    selection_reasons: dict[str, str] = Field(default_factory=dict)
    verification_flags: list[str] = Field(default_factory=list)
    canonical_venue_id: str | None = None
    venue_type: str | None = None
    venue_verified: bool = False
    staging: dict[str, Any] | None = None
    duplicate_count: int = 0
    nearby_events: list[dict[str, Any]] = Field(default_factory=list)
    weather: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_aware_datetimes(self):
        zone = ZoneInfo(self.timezone or "America/Denver")
        for field in ("start_datetime", "end_datetime", "estimated_end_datetime"):
            value = getattr(self, field)
            if value is not None:
                setattr(self, field, value.replace(tzinfo=zone) if value.tzinfo is None else value)
        for field in ("date_first_seen", "date_last_updated", "fetched_at", "source_last_updated_at", "normalized_at"):
            value = getattr(self, field)
            if value is not None and value.tzinfo is None:
                setattr(self, field, value.replace(tzinfo=ZoneInfo("UTC")))
        return self


class DemandWindow(BaseModel):
    kind: str
    start: datetime
    end: datetime
    strength: float
    reason: str


class ScoredOpportunity(BaseModel):
    event: Event
    opportunity_score: float
    confidence_score: float
    reasons: list[str]
    warnings: list[str] = Field(default_factory=list)
    demand_windows: list[DemandWindow] = Field(default_factory=list)
    staging_guidance: str | None = None
    suppressed: bool = False
    suppression_reasons: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    score_components: dict[str, float] = Field(default_factory=dict)


class DrivingSession(BaseModel):
    date: date
    start_datetime: datetime
    end_datetime: datetime
    starting_area: str | None = None
    ending_area: str | None = None
    gross_earnings: float
    tips: float = 0
    bonuses: float = 0
    miles_driven: float
    estimated_fuel_cost: float = 0
    trips_completed: int = 0
    event_targeted: str | None = None
    time_waiting: float | None = None
    deadhead_miles: float | None = None
    notes: str | None = None

    def metrics(self) -> dict[str, float | None]:
        hours = max((self.end_datetime - self.start_datetime).total_seconds() / 3600, 0)
        net = self.gross_earnings - self.estimated_fuel_cost
        return {
            "gross_per_hour": self.gross_earnings / hours if hours else None,
            "net_per_hour": net / hours if hours else None,
            "gross_per_mile": self.gross_earnings / self.miles_driven if self.miles_driven else None,
            "net_per_mile": net / self.miles_driven if self.miles_driven else None,
            "trips_per_hour": self.trips_completed / hours if hours else None,
            "deadhead_miles": self.deadhead_miles,
        }
