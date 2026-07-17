from __future__ import annotations

from datetime import datetime, timezone

from driver_dispatch.models import Event


def confidence_score(event: Event, configured_fields: list[str], maximum_age_hours: int = 168) -> tuple[float, list[str], dict[str, float]]:
    score = 18.0
    reasons, components = [], {}
    present = sum(getattr(event, field, None) is not None for field in configured_fields)
    components["field_completeness"] = 48 * present / max(len(configured_fields), 1)
    score += components["field_completeness"]
    sources = len(set(event.source_attributions or [event.source]))
    components["independent_sources"] = min(16, max(0, sources - 1) * 8)
    score += components["independent_sources"]
    if sources > 1: reasons.append(f"{sources} independent source records agree")
    attendance = 10 * (event.attendance_confidence or 0)
    if event.attendance_basis == "venue_capacity_only": attendance -= 5
    components["attendance_confidence"] = attendance
    score += attendance
    conflict_penalty = min(24, 6 * len(event.conflicting_fields))
    if conflict_penalty:
        reasons.append(f"Conflicts recorded for {', '.join(event.conflicting_fields)}")
    components["conflict_penalty"] = -conflict_penalty
    score -= conflict_penalty
    venue_penalty = 0 if event.venue_verified else 7
    components["unverified_venue"] = -venue_penalty
    score -= venue_penalty
    observed = event.source_last_updated_at or event.fetched_at
    stale_penalty = 0
    if observed:
        age = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds() / 3600
        if age > maximum_age_hours:
            stale_penalty = min(20, 5 + (age-maximum_age_hours)/24)
            reasons.append("Source information is stale")
    components["staleness"] = -stale_penalty
    score -= stale_penalty
    if sources == 1 and event.source in ("manual", "other"):
        components["single_source"] = -5
        score -= 5
    missing = [f.replace("_", " ") for f in configured_fields if getattr(event, f, None) is None]
    if missing: reasons.append("Unknown: " + ", ".join(missing))
    return round(max(0, min(100, score)), 1), reasons, components
