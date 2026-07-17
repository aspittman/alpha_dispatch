from __future__ import annotations

import re
import uuid
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt

from driver_dispatch.models import Event
from .event_normalizer import normalized_text


TOUR_WORDS = re.compile(r"\b(?:world\s+)?tour\b.*$|\b(?:19|20)\d{2}\b|\bcowboy as it gets\b", re.I)
TICKET_WORDS = re.compile(r"\b(?:tickets?|presented by|official platinum|vip package|live)\b", re.I)
SPORT_SEPARATOR = re.compile(r"\s+(?:at|vs\.?|versus|v)\s+", re.I)


def title_parts(event: Event) -> list[str]:
    title = TICKET_WORDS.sub(" ", event.name)
    title = TOUR_WORDS.sub(" ", title)
    if event.event_type == "concert":
        title = re.split(r"\s+(?:with|w/|featuring|feat\.?)\s+", title, maxsplit=1, flags=re.I)[0]
    parts = [normalized_text(part) for part in SPORT_SEPARATOR.split(title) if normalized_text(part)]
    if event.event_type in ("professional_sports", "college_sports") and len(parts) == 2:
        return sorted(parts)
    return parts


def canonical_title(event: Event) -> str:
    return " vs ".join(title_parts(event))


def _distance_miles(left: Event, right: Event) -> float | None:
    if None in (left.latitude, left.longitude, right.latitude, right.longitude):
        return None
    lat1, lon1, lat2, lon2 = map(radians, (left.latitude, left.longitude, right.latitude, right.longitude))
    a = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 3958.8 * 2 * asin(sqrt(a))


def similarity(left: Event, right: Event) -> float:
    far_apart = False
    if left.start_datetime and right.start_datetime:
        if left.start_datetime.date() != right.start_datetime.date():
            return 0
        minutes = abs((left.start_datetime - right.start_datetime).total_seconds()) / 60
        far_apart = minutes > 120
        timing = 1.0 if minutes <= 15 else 0.85 if minutes <= 60 else 0.45 if minutes <= 120 else 0
    else:
        timing = 0
    left_title, right_title = canonical_title(left), canonical_title(right)
    name = SequenceMatcher(None, left_title, right_title).ratio()
    # Tour variants normally retain the headlining artist verbatim.
    if left_title and right_title and (left_title in right_title or right_title in left_title):
        name = max(name, 0.94)
    same_venue = bool(left.canonical_venue_id and left.canonical_venue_id == right.canonical_venue_id)
    venue = 1.0 if same_venue else SequenceMatcher(None, normalized_text(left.venue_name), normalized_text(right.venue_name)).ratio() if left.venue_name and right.venue_name else 0.35
    city = 1.0 if left.city and right.city and normalized_text(left.city) == normalized_text(right.city) else 0.25
    category = 1.0 if left.event_type == right.event_type else 0.2
    distance = _distance_miles(left, right)
    coordinates = 1.0 if distance is not None and distance <= 0.25 else 0.6 if distance is None else 0
    source_id = 1.0 if left.source == right.source and left.source_event_id and left.source_event_id == right.source_event_id else 0
    score = 0.38*name + 0.20*timing + 0.16*venue + 0.08*city + 0.08*coordinates + 0.06*category + 0.04*source_id
    return min(score, 0.70) if far_apart and not source_id else score


def _completeness(event: Event) -> int:
    fields = ("start_datetime", "end_datetime", "venue_name", "venue_address", "city", "state", "latitude", "longitude", "event_url", "estimated_attendance_midpoint", "ticket_status")
    return sum(getattr(event, field) is not None for field in fields) + (2 if event.venue_verified else 0)


def merge(left: Event, right: Event) -> Event:
    primary, secondary = (left, right) if _completeness(left) >= _completeness(right) else (right, left)
    result = primary.model_copy(deep=True)
    fields = ["venue_name", "venue_address", "city", "state", "latitude", "longitude", "end_datetime", "estimated_end_datetime", "estimated_attendance", "estimated_attendance_low", "estimated_attendance_high", "estimated_attendance_midpoint", "venue_capacity", "attendance_confidence", "ticket_status", "outdoor_event", "weather", "staging", "venue_type"]
    for field in fields:
        first, second = getattr(result, field), getattr(secondary, field)
        if first is None and second is not None:
            setattr(result, field, second)
            result.selection_reasons[field] = f"Filled missing value from {secondary.source}"
        elif first is not None and second is not None and first != second:
            values = result.conflicting_fields.setdefault(field, [])
            result.conflicting_fields[field] = list(dict.fromkeys(values + [str(first), str(second)]))
            result.selection_reasons.setdefault(field, f"Selected more complete record from {primary.source}")
    if result.attendance_basis == "unknown" and secondary.attendance_basis != "unknown":
        result.attendance_basis = secondary.attendance_basis
        result.selection_reasons["attendance_basis"] = f"Selected supported basis from {secondary.source}"
    result.source_attributions = sorted(set(result.source_attributions + secondary.source_attributions + [left.source, right.source]))
    for source, ids in secondary.source_event_ids.items():
        result.source_event_ids[source] = sorted(set(result.source_event_ids.get(source, []) + ids))
    result.source_urls = sorted(set(result.source_urls + secondary.source_urls + ([secondary.event_url] if secondary.event_url else [])))
    result.source_values.update(secondary.source_values)
    result.raw_source_data = {**result.raw_source_data, secondary.source: secondary.raw_source_data}
    result.duplicate_count = left.duplicate_count + right.duplicate_count + 1
    result.selected_values = {field: str(getattr(result, field)) for field in fields if getattr(result, field) is not None}
    if secondary.status in ("canceled", "postponed"):
        result.status = secondary.status
    return result


def deduplicate(events: list[Event], threshold: float = 0.76) -> tuple[list[Event], list[tuple[Event, Event, float]]]:
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
    for event in unique:
        identity = "|".join((canonical_title(event), event.start_datetime.isoformat() if event.start_datetime else "", event.canonical_venue_id or normalized_text(event.venue_name), normalized_text(event.city)))
        event.id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"alpha-dispatch:{identity}"))
    return unique, uncertain
