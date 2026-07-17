from __future__ import annotations


def _title(name): return name.replace("_", " ").title()


def render_mobility(result):
    mode = result["mode"]
    heading = "ALPHA DISPATCH — PRE-SHIFT CHECK" if mode == "pre_shift" else "ALPHA DISPATCH — LIVE TRAFFIC REFRESH"
    lines = [heading, "", f"Generated: {result['generated_at'].isoformat()}", f"Current origin: {_title(result['origin_name'])}", "Traffic thresholds: configurable operational thresholds, not scientific facts.", ""]
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
            lines.append(f"- Relevant incidents: {len(item.incidents)}")
            lines.extend(f"  - {i.description}" for i in item.incidents[:3])
            lines.extend(f"- {reason}" for reason in item.reasons)
        lines.append("")
    lines += ["LIVE INCIDENTS", "Only incidents relevant to evaluated routes are shown above.", "", "EVENT IMPACT"]
    for event in result.get("event_impacts", []):
        lines += [event["name"], f"- Event demand score: {event['event_demand_score']}/100", f"- Mobility feasibility from current origin: {event['mobility_feasibility']}", f"- Round-trip positioning: {event['round_trip_positioning_miles']} miles" if event['round_trip_positioning_miles'] is not None else "- Round-trip positioning: unavailable", f"- Current excess delay: {event['delay_minutes']:.0f} minutes" if event['delay_minutes'] is not None else "- Current excess delay: unavailable", f"- Relevant UDOT conditions: {event['relevant_incidents']}", f"- Final driver value status: {event['final_driver_value_status']}"]
    if not result.get("event_impacts"): lines.append("No upcoming stored event could be matched to an evaluated operating zone.")
    lines += ["", "DATA STATUS", f"Google Routes: {'available' if not any(e['source']=='google' for e in result['errors']) else 'unavailable'}", f"UDOT Traffic: {'available' if not any(e['source']=='udot' for e in result['errors']) else 'unavailable'}", "Driver competition: Unknown", "Expected earnings: Unknown", "Expected tips: Unknown", "", "API RUN SUMMARY", f"Google route elements requested: {result['stats']['google']['elements']}", f"Google API calls made: {result['stats']['google']['api_calls']}", f"Google cache hits: {result['stats']['google']['cache_hits']}", f"UDOT API calls made: {result['stats']['udot']['api_calls']}", f"UDOT cache hits: {result['stats']['udot']['cache_hits']}", f"Local daily Google limit remaining: {result['stats']['google_remaining']}"]
    return "\n".join(lines)
