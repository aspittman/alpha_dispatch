def aggregate_adjustment(sessions: list, key: str) -> dict:
    """Transparent placeholder for V1 historical group adjustments."""
    grouped = {}
    for session in sessions:
        value = getattr(session, key, None)
        if value is not None: grouped.setdefault(value, []).append(session.metrics())
    return grouped

