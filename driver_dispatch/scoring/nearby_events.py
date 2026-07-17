from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from driver_dispatch.models import Event
from driver_dispatch.planning.demand_windows import demand_windows


def distance_miles(left: Event, right: Event) -> float | None:
    if None in (left.latitude, left.longitude, right.latitude, right.longitude):
        return None
    lat1, lon1, lat2, lon2 = map(radians, (left.latitude, left.longitude, right.latitude, right.longitude))
    a = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 3958.8 * 2 * asin(sqrt(a))


def assign_nearby_events(events: list[Event], radius_miles: float, minimum_attendance: int, radius_by_venue_type: dict[str, float] | None = None) -> None:
    for event in events:
        event.nearby_events = []
        windows = demand_windows(event)
        for other in events:
            if other.id == event.id or other.duplicate_count < 0:
                continue
            attendance = other.estimated_attendance_midpoint or other.estimated_attendance or 0
            if attendance < minimum_attendance:
                continue
            distance = distance_miles(event, other)
            effective_radius = (radius_by_venue_type or {}).get(event.venue_type or "", radius_miles)
            if distance is None or distance > effective_radius:
                continue
            other_windows = demand_windows(other)
            if not any(a.start < b.end and b.start < a.end for a in windows for b in other_windows):
                continue
            event.nearby_events.append({"event_id": other.id, "name": other.name, "distance_miles": round(distance, 2), "attendance_midpoint": attendance})
