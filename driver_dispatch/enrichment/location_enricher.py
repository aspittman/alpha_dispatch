from __future__ import annotations

from math import asin, cos, radians, sin, sqrt


def miles_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    value = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 3958.8 * 2 * asin(sqrt(value))


def nearest_distance(event, locations) -> float | None:
    if event.latitude is None or event.longitude is None or not locations:
        return None
    return min(miles_between(event.latitude, event.longitude, loc.latitude, loc.longitude) for loc in locations)

