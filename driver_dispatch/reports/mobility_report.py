from __future__ import annotations


def _title(name): return name.replace("_", " ").title()


def _incident_age(incident, now):
    stamp = incident.last_updated or incident.reported_time or incident.start_time
    return max(0, (now - stamp).total_seconds() / 60) if stamp else None


def render_mobility(result):
    mode = result["mode"]
    heading = "ALPHA DISPATCH — PRE-SHIFT CHECK" if mode == "pre_shift" else "ALPHA DISPATCH — LIVE TRAFFIC REFRESH"
    selected = result.get("selected_destination_count", len(result["recommendations"])); usage = result["stats"].get("usage", {})
    lines = [heading, "", f"Generated: {result['generated_at'].isoformat()}", f"Current origin: {_title(result['origin_name'])}", "Traffic thresholds: configurable operational thresholds, not scientific facts.", "", f"Destinations selected: {selected}", f"Elements required for a fresh check: {selected}"]
    lines.extend(f"- {_title(name)}: {reason}" for name, reason in result.get("destination_reasons", {}).items() if any(x.zone == name for x in result["recommendations"]))
    lines.append("")
    if mode == "live_refresh": lines += ["CHANGES SINCE LAST CHECK", *[f"- {x}" for x in result["changes"]], ""]
    usable = [x for x in result["recommendations"] if x.classification != "UNAVAILABLE"]
    local = [x for x in usable if x.classification == "PREFER"]
    lines += ["RECOMMENDATION", "Stay in Orem/Provo." if local else "Live sources do not support a confident destination ranking.", ""]
    for category in ("PREFER", "ACCEPTABLE", "AVOID", "UNAVAILABLE"):
        lines.append(category)
        items = [x for x in result["recommendations"] if x.classification == category]
        if not items: lines.append("None")
        for item in items:
            lines.append(_title(item.zone))
            if item.route:
                r = item.route
                lines += [f"- Travel time: {r.live_duration_minutes:.0f} minutes" if r.live_duration_minutes is not None else "- Travel time: unavailable", f"- Normal time: {r.static_duration_minutes:.0f} minutes" if r.static_duration_minutes is not None else "- Normal time: unavailable", f"- Delay: {r.delay_minutes:.0f} minutes" if r.delay_minutes is not None else "- Delay: unavailable", f"- Distance: {r.distance_miles:.1f} miles" if r.distance_miles is not None else "- Distance: unavailable", f"- Traffic: {r.traffic_severity}"]
            else:
                stored = result.get("static_distances", {}).get(item.zone)
                lines += ["- Google live duration: Unavailable", f"- Previously stored distance: {stored:.1f} miles" if stored is not None else "- Previously stored distance: Unavailable"]
            lines.append(f"- Relevant incidents: {len(item.incidents)}")
            lines.extend(f"  - {i.description} | corridor: {i.roadway_name or 'unknown'} | age: {_incident_age(i, result['generated_at']):.0f} minutes" if _incident_age(i, result['generated_at']) is not None else f"  - {i.description} | corridor: {i.roadway_name or 'unknown'} | age: unknown" for i in item.incidents[:3])
            lines.extend(f"- {reason}" for reason in item.reasons)
        lines.append("")
    lines += ["LIVE INCIDENTS", "Only incidents relevant to evaluated routes are shown above.", "", "EVENT IMPACT"]
    for event in result.get("event_impacts", []):
        lines += [event["name"], f"- Event demand score: {event['event_demand_score']}/100", f"- Mobility feasibility from current origin: {event['mobility_feasibility']}", f"- Round-trip positioning: {event['round_trip_positioning_miles']} miles" if event['round_trip_positioning_miles'] is not None else "- Round-trip positioning: unavailable", f"- Current excess delay: {event['delay_minutes']:.0f} minutes" if event['delay_minutes'] is not None else "- Current excess delay: unavailable", f"- Relevant UDOT conditions: {event['relevant_incidents']}", f"- Final driver value status: {event['final_driver_value_status']}"]
    if not result.get("event_impacts"): lines.append("No upcoming stored event could be matched to an evaluated operating zone.")
    routes = [x.route for x in result["recommendations"] if x.route]
    google_error = next((e["message"] for e in result["errors"] if e["source"] == "google"), None)
    source = "cached" if routes and all(r.cache_hit for r in routes) else "live" if routes else "unavailable"
    age = max((r.data_age_minutes or 0 for r in routes), default=0)
    if google_error:
        lines += ["", "Google Routes live traffic paused.", f"Reason: {google_error}", "UDOT information remains available.", "Google live travel times: Unavailable; cached results are used when available."]
    daily_limit, monthly_limit = usage.get("google_daily_limit"), usage.get("google_monthly_limit")
    remaining = usage.get("monthly_remaining"); at6 = remaining // 6 if remaining is not None else "unavailable"; at8 = remaining // 8 if remaining is not None else "unavailable"
    lines += ["", "DATA STATUS", f"Google Routes: {source}, {age:.0f} minutes old" if routes else "Google Routes: unavailable", f"UDOT Traffic: {'available' if not any(e['source']=='udot' for e in result['errors']) else 'unavailable'}", "Driver competition: Unknown", "Expected earnings: Unknown", "Expected tips: Unknown", "", "API USAGE", f"Google Routes today: {usage.get('google_today', 0)} / {daily_limit if daily_limit is not None else 'not configured'} elements", f"Google Routes this month: {usage.get('google_month', 0)} / {monthly_limit if monthly_limit is not None else 'not configured'} elements", f"Monthly safety remaining: {remaining if remaining is not None else 'unavailable'} elements", f"Estimated full refreshes remaining: {at6} at 6 destinations; {at8} at 8 destinations", f"UDOT calls today: {usage.get('udot_today', 0)}", "", "Current data:", f"Google Routes: {source}, {age:.0f} minutes old" if routes else "Google Routes: unavailable", f"UDOT: {'live/cached' if not any(e['source']=='udot' for e in result['errors']) else 'unavailable'}", f"Google elements used by this refresh: {result['stats']['google']['elements']}", "", "Refresh only while safely parked. Fresh cached results are reused; an enabled force refresh requires confirmation and consumes the displayed elements."]
    return "\n".join(lines)
