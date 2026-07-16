from __future__ import annotations

import uuid
from difflib import SequenceMatcher

from driver_dispatch.models import Event
from .event_normalizer import normalized_text


def similarity(left: Event, right: Event) -> float:
    name = SequenceMatcher(None, normalized_text(left.name), normalized_text(right.name)).ratio()
    venue = SequenceMatcher(None, normalized_text(left.venue_name), normalized_text(right.venue_name)).ratio() if left.venue_name and right.venue_name else 0.35
    city = 1.0 if left.city and right.city and normalized_text(left.city) == normalized_text(right.city) else 0.3
    if left.start_datetime and right.start_datetime:
        minutes = abs((left.start_datetime - right.start_datetime).total_seconds()) / 60
        timing = 1.0 if minutes <= 15 else 0.7 if minutes <= 60 else 0
    else:
        timing = 0
    source_id = 1.0 if left.source == right.source and left.source_event_id and left.source_event_id == right.source_event_id else 0
    return 0.42 * name + 0.22 * venue + 0.22 * timing + 0.08 * city + 0.06 * source_id


def merge(primary: Event, secondary: Event) -> Event:
    result = primary.model_copy(deep=True)
    complementary = ["venue_name", "venue_address", "city", "state", "latitude", "longitude", "end_datetime", "estimated_end_datetime", "estimated_attendance", "venue_capacity", "attendance_confidence", "ticket_status", "outdoor_event", "event_url", "weather"]
    for field in complementary:
        if getattr(result, field) is None and getattr(secondary, field) is not None:
            setattr(result, field, getattr(secondary, field))
    result.source_attributions = sorted(set(result.source_attributions + secondary.source_attributions + [primary.source, secondary.source]))
    result.raw_source_data = {primary.source: primary.raw_source_data, secondary.source: secondary.raw_source_data}
    if secondary.status in ("canceled", "postponed"):
        result.status = secondary.status
    return result


def deduplicate(events: list[Event], threshold: float = 0.78) -> tuple[list[Event], list[tuple[Event, Event, float]]]:
    unique: list[Event] = []
    uncertain = []
    for event in events:
        event.id = event.id or str(uuid.uuid4())
        scores = [(similarity(event, existing), index) for index, existing in enumerate(unique)]
        best = max(scores, default=(0, -1))
        if best[0] >= threshold:
            unique[best[1]] = merge(unique[best[1]], event)
        else:
            if 0.62 <= best[0] < threshold:
                uncertain.append((unique[best[1]], event, best[0]))
            unique.append(event)
    return unique, uncertain
