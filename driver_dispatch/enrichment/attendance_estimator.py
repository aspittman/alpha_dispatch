from driver_dispatch.models import Event


DEFAULT_OCCUPANCY = {"concert": (0.35, 0.70), "professional_sports": (0.40, 0.75), "college_sports": (0.35, 0.70), "convention": (0.20, 0.50), "theater": (0.35, 0.70), "comedy": (0.35, 0.70)}


def estimate_attendance(event: Event) -> Event:
    if event.estimated_attendance is not None and event.estimated_attendance_midpoint is None:
        event.estimated_attendance_low = event.estimated_attendance_low or event.estimated_attendance
        event.estimated_attendance_high = event.estimated_attendance_high or event.estimated_attendance
        event.estimated_attendance_midpoint = event.estimated_attendance
        event.attendance_basis = "source_estimate" if event.attendance_basis == "unknown" else event.attendance_basis
        event.attendance_confidence = event.attendance_confidence or 0.6
    elif event.estimated_attendance_midpoint is None and event.venue_capacity:
        low_ratio, high_ratio = DEFAULT_OCCUPANCY.get(str(event.event_type), (0.20, 0.50))
        event.estimated_attendance_low = round(event.venue_capacity * low_ratio)
        event.estimated_attendance_high = round(event.venue_capacity * high_ratio)
        event.estimated_attendance_midpoint = round((event.estimated_attendance_low + event.estimated_attendance_high) / 2)
        # Legacy field remains unset so capacity fallback cannot be mistaken for a confirmed estimate.
        event.estimated_attendance = None
        event.attendance_basis = "venue_capacity_only"
        event.attendance_confidence = min(event.attendance_confidence or 0.25, 0.25)
    return event
