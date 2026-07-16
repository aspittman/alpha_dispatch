from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class Event(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    id: str | None = None
    source: str
    source_event_id: str | None = None
    source_attributions: list[str] = Field(default_factory=list)
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
    estimated_attendance: int | None = None
    venue_capacity: int | None = None
    attendance_confidence: float | None = None
    ticket_status: str | None = None
    outdoor_event: bool | None = None
    event_url: str | None = None
    date_first_seen: datetime | None = None
    date_last_updated: datetime | None = None
    status: str = "scheduled"
    raw_source_data: dict[str, Any] = Field(default_factory=dict)
    weather: dict[str, Any] | None = None


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
