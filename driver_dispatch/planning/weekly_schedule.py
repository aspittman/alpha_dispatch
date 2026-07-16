from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from driver_dispatch.models import ScoredOpportunity
from .conflict_detector import conflicts


def build_schedule(opportunities: list[ScoredOpportunity], maximum_hours: float) -> dict:
    candidates = sorted((o for o in opportunities if not o.suppressed), key=lambda o: (o.opportunity_score, o.confidence_score), reverse=True)
    selected, conflict_notes = [], []
    total_hours = 0.0
    for item in candidates:
        if not item.demand_windows: continue
        start = min(w.start for w in item.demand_windows)
        end = max(w.end for w in item.demand_windows)
        hours = (end - start).total_seconds() / 3600
        collisions = [existing for existing in selected if conflicts(item, existing)]
        if collisions:
            conflict_notes.append({"event": item.event.name, "conflicts_with": collisions[0].event.name, "reason": "Overlapping demand windows; higher-ranked opportunity retained."})
            continue
        if total_hours + hours > maximum_hours: continue
        selected.append(item); total_hours += hours
    by_day = defaultdict(list)
    for item in selected:
        by_day[item.event.start_datetime.strftime("%A")].append(item)
    return {"selected": selected, "by_day": dict(by_day), "conflicts": conflict_notes, "total_hours": round(total_hours, 1)}

