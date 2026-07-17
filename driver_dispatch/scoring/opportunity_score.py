from __future__ import annotations

from driver_dispatch.enrichment.location_enricher import nearest_distance
from driver_dispatch.models import Event, ScoredOpportunity
from driver_dispatch.planning.demand_windows import demand_windows
from driver_dispatch.planning.staging_advisor import staging_guidance
from .confidence_score import confidence_score
from .rules import suppressions


def score_event(event: Event, settings, overlap_count: int | None = None) -> ScoredOpportunity:
    config = settings.scoring
    components: dict[str, float] = {"base": 12.0}
    reasons, warnings = [], []
    category = config.get("category_weights", {}).get(str(event.event_type), 5)
    components["category"] = category
    reasons.append(f"Category: +{category:g} ({str(event.event_type).replace('_', ' ')})")
    attendance = event.estimated_attendance_midpoint or event.estimated_attendance
    attendance_points = 0
    if attendance is not None:
        for threshold, value in config.get("attendance_breakpoints", []):
            if attendance >= threshold: attendance_points = value
        reliability = 0.45 + 0.55 * (event.attendance_confidence or 0)
        attendance_points *= reliability
        reasons.append(f"Attendance: +{attendance_points:.1f} ({attendance:,} midpoint; {event.attendance_basis})")
    else:
        warnings.append("Attendance is unknown")
    components["attendance"] = attendance_points
    day_points = timing_points = 0
    if event.start_datetime:
        day_points = config.get("day_weights", {}).get(event.start_datetime.strftime("%A"), 0)
        timing_points = 6 if event.start_datetime.hour >= 18 else 0
        reasons.append(f"Day/timing: +{day_points + timing_points:g} ({event.start_datetime:%A}, local time)")
    components["day"] = day_points
    components["timing"] = timing_points
    ticket_points = 7 if event.ticket_status and event.ticket_status.lower() in ("soldout", "sold_out", "offsale") else 0
    components["ticket_status"] = ticket_points
    nearby_count = len(event.nearby_events) if overlap_count is None else overlap_count
    nearby_points = min(12, nearby_count * 4)
    components["nearby_events"] = nearby_points
    if nearby_count:
        names = ", ".join(item.get("name", "event") for item in event.nearby_events[:3])
        reasons.append(f"Nearby overlap: +{nearby_points:g}" + (f" ({names})" if names else ""))
    weather_demand = weather_safety = 0.0
    if event.weather:
        risk = event.weather.get("risk", 0)
        precip = event.weather.get("precipitation_probability") or 0
        weather_demand = 4 if 25 <= precip <= 70 and risk < 60 else 0
        weather_safety = -min(30, risk / 3) if risk > 35 else 0
        reasons.append(f"Weather demand: {weather_demand:+g}; driving safety: {weather_safety:+.1f}")
    components["weather_demand"] = weather_demand
    components["weather_safety"] = weather_safety
    distance = nearest_distance(event, settings.locations)
    distance_adjustment = -min(15, distance / 5) if distance is not None else 0
    components["distance"] = distance_adjustment
    confidence, confidence_reasons, confidence_components = confidence_score(event, config.get("confidence_fields", []), settings.app.maximum_source_age_hours)
    reasons.extend(confidence_reasons)
    components["data_quality"] = 0  # Confidence remains separate and never masks opportunity.
    score = round(max(0, min(100, sum(components.values()))), 1)
    suppressed_reasons = suppressions(event, settings)
    if score < settings.app.minimum_opportunity_score: suppressed_reasons.append("Below opportunity threshold")
    if confidence < settings.app.minimum_confidence_score: suppressed_reasons.append("Below confidence threshold")
    review = list(event.verification_flags)
    if event.conflicting_fields: review.append("Conflicting source data could change this recommendation")
    return ScoredOpportunity(event=event, opportunity_score=score, event_demand_score=score, confidence_score=confidence, reasons=reasons, warnings=warnings, demand_windows=demand_windows(event), staging_guidance=staging_guidance(event, settings.venues), suppressed=bool(suppressed_reasons), suppression_reasons=suppressed_reasons, review_reasons=review, score_components={**components, **{f"confidence_{k}": v for k, v in confidence_components.items()}})
