from driver_dispatch.models import Event


DEFAULT_OCCUPANCY = {"concert": 0.78, "professional_sports": 0.72, "college_sports": 0.68, "convention": 0.45, "theater": 0.70, "comedy": 0.70}


def estimate_attendance(event: Event) -> Event:
    if event.estimated_attendance is None and event.venue_capacity:
        ratio = DEFAULT_OCCUPANCY.get(str(event.event_type), 0.50)
        event.estimated_attendance = round(event.venue_capacity * ratio)
        event.attendance_confidence = min(event.attendance_confidence or 0.45, 0.45)
    return event

