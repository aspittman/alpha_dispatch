from __future__ import annotations

from datetime import date, datetime, time, timedelta

from driver_dispatch.models import ScoredOpportunity


def merge_intervals(intervals: list[tuple[datetime, datetime]], adjacent_minutes: int = 30) -> list[tuple[datetime, datetime]]:
    merged: list[list[datetime]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + timedelta(minutes=adjacent_minutes):
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def interval_hours(intervals: list[tuple[datetime, datetime]]) -> float:
    return sum((end-start).total_seconds()/3600 for start, end in intervals)


def build_schedule(opportunities: list[ScoredOpportunity], maximum_hours: float, week_start: date | None = None, maximum_daily_hours: float = 8, adjacent_minutes: int = 30) -> dict:
    dated = [o for o in opportunities if o.event.start_datetime]
    if week_start is None:
        week_start = min((o.event.start_datetime.date() for o in dated), default=date.today())
    candidates = sorted((o for o in dated if not o.suppressed), key=lambda o: (o.opportunity_score, o.confidence_score), reverse=True)
    selected: list[ScoredOpportunity] = []
    weekly_hours = 0.0
    day_intervals: dict[date, list[tuple[datetime, datetime]]] = {}
    for item in candidates:
        day = item.event.start_datetime.date()
        proposed = [(w.start, w.end) for w in item.demand_windows]
        merged = merge_intervals(day_intervals.get(day, []) + proposed, adjacent_minutes)
        new_day_hours = min(interval_hours(merged), maximum_daily_hours)
        old_day_hours = min(interval_hours(day_intervals.get(day, [])), maximum_daily_hours)
        incremental = new_day_hours - old_day_hours
        if weekly_hours + incremental > maximum_hours:
            continue
        selected.append(item)
        day_intervals[day] = merged
        weekly_hours += incremental
    plans = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        recommended = sorted([o for o in selected if o.event.start_datetime.date() == day], key=lambda o: o.opportunity_score, reverse=True)
        review = sorted([o for o in dated if o.event.start_datetime.date() == day and o.suppressed and o.review_reasons], key=lambda o: o.opportunity_score, reverse=True)
        intervals = day_intervals.get(day, [])
        if recommended:
            primary = recommended[0]
            status = "Primary driving day" if primary.opportunity_score >= 60 else "Optional driving day"
            transition = "Remain in the primary event area"
            if recommended[1:]:
                transition = f"Transition toward {recommended[1].event.city or recommended[1].event.venue_name or 'the secondary opportunity area'} only after the primary window"
            plans.append({"date": day, "day": day.strftime("%A"), "status": status, "start": intervals[0][0], "end": intervals[-1][1], "hours": round(min(interval_hours(intervals), maximum_daily_hours), 1), "intervals": intervals, "primary": primary, "secondary": recommended[1:], "transition": transition, "reason": f"Highest qualified opportunity is {primary.event.name} ({primary.opportunity_score}/100).", "risks": primary.warnings + primary.review_reasons})
        elif review:
            plans.append({"date": day, "day": day.strftime("%A"), "status": "Verify before driving", "hours": 0.0, "primary": review[0], "secondary": [], "reason": "; ".join(review[0].review_reasons[:2]), "risks": review[0].review_reasons})
        else:
            plans.append({"date": day, "day": day.strftime("%A"), "status": "Skip", "hours": 0.0, "primary": None, "secondary": [], "reason": "No events exceeded the configured opportunity and confidence thresholds.", "risks": []})
    return {"selected": selected, "by_day": {p["day"]: [p["primary"], *p["secondary"]] for p in plans if p["primary"] and p["status"] in ("Primary driving day", "Optional driving day")}, "plans": plans, "conflicts": [], "total_hours": round(sum(p["hours"] for p in plans), 1), "hour_calculation": "Union of overlapping/adjacent demand windows, capped by daily and weekly limits."}
