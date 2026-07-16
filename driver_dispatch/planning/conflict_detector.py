from driver_dispatch.models import ScoredOpportunity


def conflicts(left: ScoredOpportunity, right: ScoredOpportunity) -> bool:
    if not left.demand_windows or not right.demand_windows:
        return False
    return any(a.start < b.end and b.start < a.end for a in left.demand_windows for b in right.demand_windows)

