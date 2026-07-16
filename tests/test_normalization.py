from datetime import datetime

from driver_dispatch.models import Event
from driver_dispatch.normalization.event_normalizer import normalize_event, normalized_text


def test_normalization_and_timezone():
    event = Event(source="x", name="  The  Big—Show ", city="salt lake CITY", start_datetime=datetime(2026, 1, 2, 20))
    result = normalize_event(event)
    assert result.name == "The Big—Show"
    assert result.city == "Salt Lake City"
    assert result.start_datetime.utcoffset() is not None
    assert normalized_text(result.name) == "big show"


def test_missing_fields_remain_unknown():
    result = normalize_event(Event(source="x", name="Known name"))
    assert result.venue_name is None and result.estimated_attendance is None

