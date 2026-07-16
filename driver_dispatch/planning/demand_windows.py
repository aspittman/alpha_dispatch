from __future__ import annotations

from datetime import timedelta

from driver_dispatch.models import DemandWindow, Event


RULES = {
    "concert": (120, 30, 90, 90, 3.0),
    "professional_sports": (105, 20, 75, 90, 3.0),
    "college_sports": (150, 30, 90, 120, 3.5),
    "convention": (75, 15, 45, 75, 8.0),
    "trade_show": (75, 15, 45, 75, 7.0),
    "festival": (120, 30, 90, 120, 6.0),
    "theater": (75, 15, 30, 60, 2.5),
    "comedy": (75, 15, 30, 75, 2.0),
}


def estimated_end(event: Event):
    if event.end_datetime: return event.end_datetime
    if event.estimated_end_datetime: return event.estimated_end_datetime
    if event.start_datetime:
        return event.start_datetime + timedelta(hours=RULES.get(str(event.event_type), (90, 15, 45, 75, 3.0))[4])
    return None


def demand_windows(event: Event) -> list[DemandWindow]:
    if not event.start_datetime:
        return []
    before, after_start, depart_before, depart_after, _ = RULES.get(str(event.event_type), (90, 15, 45, 75, 3.0))
    end = estimated_end(event)
    windows = [DemandWindow(kind="arrival", start=event.start_datetime - timedelta(minutes=before), end=event.start_datetime + timedelta(minutes=after_start), strength=0.7, reason=f"Typical {event.event_type} arrival pattern; actual demand is unknown.")]
    if end:
        windows.append(DemandWindow(kind="departure", start=end - timedelta(minutes=depart_before), end=end + timedelta(minutes=depart_after), strength=0.9 if event.event_type in ("concert", "professional_sports") else 0.7, reason="Estimated ending and dispersal window; confirm event timing before driving."))
    if event.event_type in ("concert", "convention", "festival") and end:
        windows.append(DemandWindow(kind="secondary", start=end, end=end + timedelta(hours=2), strength=0.5, reason="Possible restaurant, hotel, or nightlife spillover."))
    return windows

