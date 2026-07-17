from __future__ import annotations

from driver_dispatch.models import Event
from driver_dispatch.normalization.event_normalizer import normalized_text


def _find(event: Event, venues: dict):
    needle = normalized_text(event.venue_name)
    for venue_id, value in venues.items():
        aliases = [venue_id, value.get("canonical_name", ""), *value.get("aliases", [])]
        if needle and needle in {normalized_text(alias) for alias in aliases}:
            return venue_id, value
    return None, None


def enrich_venue(event: Event, venues: dict) -> Event:
    venue_id, known = _find(event, venues)
    if not known:
        return event
    event.canonical_venue_id = venue_id
    event.venue_verified = True
    mapping = {"venue_name": "canonical_name", "venue_address": "address", "city": "city", "state": "state", "latitude": "latitude", "longitude": "longitude", "venue_capacity": "capacity", "venue_type": "venue_type", "staging": "staging"}
    for field, config_field in mapping.items():
        canonical = known.get(config_field)
        supplied = getattr(event, field)
        if canonical is None:
            continue
        if supplied is not None and supplied != canonical and field not in ("venue_name", "staging"):
            event.conflicting_fields.setdefault(field, []).extend([supplied, canonical])
            event.verification_flags.append(f"Source {field.replace('_', ' ')} conflicted with canonical venue")
        setattr(event, field, canonical)
        event.selection_reasons[field] = "Canonical verified venue configuration"
    event.selected_values.update({field: getattr(event, field) for field in mapping if getattr(event, field) is not None})
    return event
