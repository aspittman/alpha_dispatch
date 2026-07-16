from driver_dispatch.models import Event


DISCLAIMER = "Use only legal, safe public waiting areas and follow platform, venue, airport, and local rules."


def staging_guidance(event: Event, venues: dict) -> str:
    specific = venues.get(event.venue_name or "", {}).get("staging")
    if specific:
        return f"{specific} {DISCLAIMER}"
    if event.event_type in ("concert", "professional_sports", "college_sports"):
        advice = "Stage outside the immediate venue congestion zone, preferably near a legal hotel or restaurant corridor."
    elif event.event_type in ("convention", "trade_show"):
        advice = "Consider legal public areas serving nearby hotels and restaurants rather than the venue entrance."
    else:
        advice = "Stay outside closures and congestion; use driver judgment when selecting a general nearby commercial area."
    return f"{advice} {DISCLAIMER}"

