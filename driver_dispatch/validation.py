from __future__ import annotations

from datetime import datetime, timezone

from driver_dispatch.enrichment.location_enricher import nearest_distance
from driver_dispatch.models import Event
from driver_dispatch.planning.demand_windows import demand_windows


def validation_failures(event: Event, settings, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    reasons = []
    if not event.start_datetime or event.start_datetime.tzinfo is None:
        reasons.append("Missing timezone-aware local datetime")
    if not event.venue_name and not event.city:
        reasons.append("No canonical or usable venue")
    if event.latitude is not None and not (-90 <= event.latitude <= 90) or event.longitude is not None and not (-180 <= event.longitude <= 180):
        reasons.append("Venue coordinates are implausible")
    if event.estimated_attendance is not None and event.attendance_basis == "venue_capacity_only":
        reasons.append("Attendance was incorrectly copied from venue capacity")
    if event.start_datetime and event.start_datetime.astimezone(timezone.utc) <= now:
        reasons.append("Event is already over or has started")
    windows = demand_windows(event)
    arrival = [w for w in windows if w.kind == "arrival"]
    departure = [w for w in windows if w.kind == "departure"]
    if arrival and departure and departure[0].start <= arrival[0].start:
        reasons.append("Departure window does not follow arrival window")
    distance = nearest_distance(event, settings.locations)
    if distance is not None and distance > settings.app.maximum_driving_distance_miles:
        reasons.append("Outside configured operating market")
    observed = event.source_last_updated_at or event.fetched_at
    if observed and (now - observed.astimezone(timezone.utc)).total_seconds() > settings.app.maximum_source_age_hours * 3600:
        reasons.append("Source data is too stale")
    return reasons
