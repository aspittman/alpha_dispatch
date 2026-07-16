from datetime import timedelta

from driver_dispatch.models import ScoredOpportunity
from driver_dispatch.planning.conflict_detector import conflicts
from driver_dispatch.planning.demand_windows import demand_windows


def test_concert_demand_windows(event):
    windows = demand_windows(event)
    assert [w.kind for w in windows] == ["arrival", "departure", "secondary"]
    assert windows[0].start == event.start_datetime - timedelta(minutes=120)


def test_schedule_conflict(event):
    windows = demand_windows(event)
    one = ScoredOpportunity(event=event, opportunity_score=80, confidence_score=70, reasons=[], demand_windows=windows)
    two = one.model_copy(deep=True); two.event.name = "Nearby Game"
    assert conflicts(one, two)

