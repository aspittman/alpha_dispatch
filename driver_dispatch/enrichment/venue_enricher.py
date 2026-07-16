from driver_dispatch.models import Event


def enrich_venue(event: Event, venues: dict) -> Event:
    known = venues.get(event.venue_name or "", {})
    if event.venue_capacity is None:
        event.venue_capacity = known.get("capacity")
    return event

