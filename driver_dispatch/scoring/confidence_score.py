from driver_dispatch.models import Event


def confidence_score(event: Event, configured_fields: list[str]) -> tuple[float, list[str]]:
    base = 18
    reasons = []
    present = sum(getattr(event, field, None) is not None for field in configured_fields)
    base += 55 * present / max(len(configured_fields), 1)
    sources = len(set(event.source_attributions or [event.source]))
    if sources > 1:
        base += min(15, (sources - 1) * 8)
        reasons.append(f"Confirmed or enriched by {sources} sources")
    if event.attendance_confidence is not None:
        base += 12 * event.attendance_confidence
    if event.start_datetime and event.venue_name:
        reasons.append("Event time and venue are known")
    missing = [f.replace("_", " ") for f in configured_fields if getattr(event, f, None) is None]
    if missing:
        reasons.append("Unknown: " + ", ".join(missing))
    return round(min(100, base), 1), reasons

