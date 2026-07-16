from __future__ import annotations

from driver_dispatch.enrichment.location_enricher import nearest_distance
from driver_dispatch.models import Event, ScoredOpportunity
from driver_dispatch.planning.demand_windows import demand_windows
from driver_dispatch.planning.staging_advisor import staging_guidance
from .confidence_score import confidence_score
from .rules import suppressions


def score_event(event: Event, settings, overlap_count: int = 0) -> ScoredOpportunity:
    config = settings.scoring
    score = 12.0
    reasons, warnings = [], []
    category = config.get("category_weights", {}).get(str(event.event_type), 5)
    score += category
    reasons.append(f"{str(event.event_type).replace('_', ' ').title()} category contributes {category} points")
    if event.estimated_attendance is not None:
        points = 0
        for threshold, value in config.get("attendance_breakpoints", []):
            if event.estimated_attendance >= threshold: points = value
        score += points
        reasons.append(f"Estimated attendance {event.estimated_attendance:,} contributes {points} points")
    else:
        warnings.append("Attendance is unknown")
    if event.start_datetime:
        day_points = config.get("day_weights", {}).get(event.start_datetime.strftime("%A"), 0)
        score += day_points
        reasons.append(f"{event.start_datetime.strftime('%A')} contributes {day_points} points")
        if event.start_datetime.hour >= 18: score += 6; reasons.append("Evening timing contributes 6 points")
    if event.ticket_status and event.ticket_status.lower() in ("soldout", "sold_out", "offsale"):
        score += 7; reasons.append("Ticket status suggests strong attendance")
    if overlap_count:
        boost = min(12, overlap_count * 4); score += boost; reasons.append(f"{overlap_count} nearby overlapping event(s) contribute {boost} points")
    if event.weather:
        risk = event.weather.get("risk", 0)
        text = event.weather.get("short_forecast", "weather")
        if 10 <= risk <= 35: score += 3; reasons.append(f"{text} may modestly increase ride interest")
        elif risk > 35: score -= min(25, risk / 3); warnings.append(f"Weather safety/efficiency risk: {text}")
    distance = nearest_distance(event, settings.locations)
    if distance is not None:
        penalty = min(15, distance / 5); score -= penalty
        reasons.append(f"Distance from a configured market reduces score by {penalty:.1f}")
    confidence, confidence_reasons = confidence_score(event, config.get("confidence_fields", []))
    reasons.extend(confidence_reasons)
    score *= 0.72 + 0.28 * confidence / 100
    suppressed_reasons = suppressions(event, settings)
    score = round(max(0, min(100, score)), 1)
    if score < settings.app.minimum_opportunity_score: suppressed_reasons.append("Opportunity score is below configured minimum")
    if confidence < settings.app.minimum_confidence_score: suppressed_reasons.append("Confidence score is below configured minimum")
    if score >= 70 and confidence < 50: warnings.append("High-upside, low-confidence: manually verify before acting")
    return ScoredOpportunity(event=event, opportunity_score=score, confidence_score=confidence, reasons=reasons, warnings=warnings, demand_windows=demand_windows(event), staging_guidance=staging_guidance(event, settings.venues), suppressed=bool(suppressed_reasons), suppression_reasons=suppressed_reasons)
