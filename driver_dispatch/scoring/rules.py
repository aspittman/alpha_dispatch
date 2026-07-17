from __future__ import annotations

from datetime import timedelta

from driver_dispatch.enrichment.location_enricher import nearest_distance
from driver_dispatch.models import Event
from driver_dispatch.planning.demand_windows import estimated_end


def suppressions(event: Event, settings) -> list[str]:
    reasons = []
    if event.status.lower() in ("canceled", "cancelled", "postponed"):
        reasons.append(f"Event is {event.status}")
    if not event.start_datetime:
        reasons.append("Start date/time is unknown")
    if not event.venue_name and not event.city:
        reasons.append("Venue and city are unknown")
    if event.estimated_attendance is not None and event.estimated_attendance < settings.app.minimum_estimated_attendance:
        reasons.append("Estimated attendance is below configured minimum")
    distance = nearest_distance(event, settings.locations)
    if distance is not None and distance > settings.app.maximum_driving_distance_miles:
        reasons.append(f"Approximately {distance:.0f} miles outside configured operating areas")
    if event.weather and event.weather.get("risk", 0) > settings.app.maximum_weather_risk:
        reasons.append("Weather risk exceeds configured safety limit")
    end = estimated_end(event)
    start, finish = settings.app.permitted_start_hour, settings.app.permitted_end_hour
    if end and start is not None and finish is not None:
        hour = end.hour
        permitted = hour >= start or hour < finish if start > finish else start <= hour < finish
        if not permitted:
            reasons.append("Estimated ending is outside permitted driving hours")
    return reasons
