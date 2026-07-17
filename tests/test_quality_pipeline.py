from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from driver_dispatch.enrichment.attendance_estimator import estimate_attendance
from driver_dispatch.enrichment.venue_enricher import enrich_venue
from driver_dispatch.models import Event, ScoredOpportunity
from driver_dispatch.normalization import deduplicate, normalize_event
from driver_dispatch.planning.demand_windows import demand_windows
from driver_dispatch.planning.weekly_schedule import build_schedule
from driver_dispatch.reports.weekly_report import render_reports
from driver_dispatch.scoring.nearby_events import assign_nearby_events
from driver_dispatch.scoring.opportunity_score import score_event
from driver_dispatch.sources.seatgeek import SeatGeekSource


def source_event(name, when, kind="concert", venue="Delta Center", source="a"):
    return normalize_event(Event(source=source, source_event_id=source, name=name, event_type=kind, venue_name=venue, city="Salt Lake City", latitude=40.7683, longitude=-111.9011, start_datetime=when))


def test_utc_to_mountain_daylight_and_local_day_assignment():
    event = source_event("Evening Event", "2026-07-18T01:00:00Z")
    assert event.start_datetime.strftime("%A, %B %-d at %-I:%M %p %Z") == "Friday, July 17 at 7:00 PM MDT"


def test_utc_to_mountain_standard_time():
    event = source_event("Winter Event", "2026-01-18T03:00:00Z")
    assert event.start_datetime.isoformat() == "2026-01-17T20:00:00-07:00"
    assert event.start_datetime.tzname() == "MST"


def test_seatgeek_naive_datetime_utc_is_explicitly_utc():
    value = SeatGeekSource._utc_datetime("2026-07-18T01:00:00")
    assert value.tzinfo == timezone.utc
    assert normalize_event(Event(source="seatgeek", name="Hilary Duff", start_datetime=value)).start_datetime.strftime("%A %-I:%M %p %Z") == "Friday 7:00 PM MDT"


def test_duplicate_sports_and_concert_titles_merge():
    sports = [source_event("Orlando Pride at Utah Royals FC", "2026-07-18T01:00:00Z", "professional_sports", "America First Field", "tm"), source_event("Utah Royals FC vs. Orlando Pride", "2026-07-17T19:00:00-06:00", "professional_sports", "America First Field", "sg")]
    concerts = [source_event("Riley Green", "2026-07-18T02:00:00Z", source="tm"), source_event("Riley Green: Cowboy As It Gets Tour 2026", "2026-07-17T20:00:00-06:00", source="sg")]
    assert len(deduplicate(sports)[0]) == 1
    merged = deduplicate(concerts)[0]
    assert len(merged) == 1 and set(merged[0].source_attributions) == {"tm", "sg"}
    hilary = [source_event("Hilary Duff: the lucky me tour 2026", "2026-07-18T01:00:00Z", source="tm"), source_event("Hilary Duff with La Roux and Jade LeMac", "2026-07-17T19:00:00-06:00", source="sg")]
    assert len(deduplicate(hilary)[0]) == 1


def test_repeated_theater_performances_at_different_times_remain_separate():
    matinée = source_event("Hamilton", "2026-07-18T14:00:00-06:00", "theater")
    evening = source_event("Hamilton", "2026-07-18T20:00:00-06:00", "theater", source="b")
    assert len(deduplicate([matinée, evening])[0]) == 2


def test_canonical_venue_alias_overrides_conflicting_address(settings):
    settings.venues = {"america_first_field": {"canonical_name": "America First Field", "aliases": ["Rio Tinto Stadium"], "address": "9256 South State Street", "city": "Sandy", "state": "UT", "latitude": 40.5829, "longitude": -111.8934, "capacity": 20213, "venue_type": "stadium"}}
    event = source_event("Game", "2026-07-18T01:00:00Z", "professional_sports", "Rio Tinto Stadium")
    event.venue_address = "Wrong address"
    result = enrich_venue(event, settings.venues)
    assert result.venue_name == "America First Field"
    assert result.venue_address == "9256 South State Street"
    assert "venue_address" in result.conflicting_fields and result.venue_verified


def test_capacity_fallback_is_range_not_confirmed_attendance(event):
    result = estimate_attendance(event.model_copy(update={"estimated_attendance": None, "venue_capacity": 20000, "attendance_confidence": None}))
    assert result.estimated_attendance is None
    assert result.estimated_attendance_low < result.estimated_attendance_high < result.venue_capacity
    assert result.attendance_basis == "venue_capacity_only" and result.attendance_confidence <= .25


def test_nearby_scoring_runs_on_deduplicated_events():
    primary = source_event("Primary", "2026-07-18T02:00:00Z")
    primary.estimated_attendance_midpoint = 5000
    duplicate = primary.model_copy(deep=True); duplicate.source = "b"; duplicate.source_event_id = "b"
    other = source_event("Nearby Theater", "2026-07-18T02:15:00Z", "theater", source="c"); other.estimated_attendance_midpoint = 1000
    unique, _ = deduplicate([primary, duplicate, other])
    assign_nearby_events(unique, 3, 500)
    assert len(unique) == 2
    assert all(len(event.nearby_events) == 1 for event in unique)


def test_weekly_hours_merge_overlapping_windows(event):
    first = ScoredOpportunity(event=event, opportunity_score=80, confidence_score=80, reasons=[], demand_windows=demand_windows(event))
    second_event = event.model_copy(deep=True); second_event.id = "second"; second_event.name = "Second"; second_event.start_datetime += timedelta(minutes=30)
    second = ScoredOpportunity(event=second_event, opportunity_score=70, confidence_score=80, reasons=[], demand_windows=demand_windows(second_event))
    schedule = build_schedule([first, second], 20, event.start_datetime.date())
    naive_sum = sum((w.end-w.start).total_seconds()/3600 for item in (first, second) for w in item.demand_windows)
    assert schedule["total_hours"] < naive_sum
    assert len(schedule["plans"]) == 7


def test_weather_adjustments_and_conflict_confidence(event, settings):
    storm = event.model_copy(update={"weather": {"risk": 75, "precipitation_probability": 80, "short_forecast": "Thunderstorm"}, "conflicting_fields": {"start_datetime": ["a", "b"]}})
    result = score_event(storm, settings)
    assert result.score_components["weather_safety"] < 0
    assert result.score_components["weather_demand"] == 0
    assert result.score_components["confidence_conflict_penalty"] < 0


def test_feature_status_and_rejection_summary(event, settings, tmp_path):
    rejected = score_event(event.model_copy(update={"status": "canceled"}), settings)
    rejected.review_reasons.append("Conflicting event time")
    schedule = build_schedule([rejected], 20, date(2026, 7, 17))
    _, text = render_reports(date(2026, 7, 17), [rejected], schedule, [], tmp_path, {"airport": "not_implemented", "weather": "source_failed", "traffic": "not_configured"})
    output = text.read_text()
    assert "Weather intelligence: Source failed during this run." in output
    assert "Rejected events: 1" in output and output.count("Example Concert") <= 2
