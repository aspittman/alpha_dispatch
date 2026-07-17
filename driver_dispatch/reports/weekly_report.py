from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


STATUS_LABELS = {"not_implemented": "Not implemented in V1", "not_configured": "Not configured", "source_failed": "Source failed during this run", "no_data_found": "No data found", "data_stale": "Data stale", "available": "Available"}


def _location(event):
    parts = [event.venue_name, event.venue_address, event.city, event.state]
    return ", ".join(dict.fromkeys(str(part) for part in parts if part)) or "Location unknown"


def _fmt(value):
    return value.strftime("%a %b %-d, %-I:%M %p %Z") if value else "Time unknown"


def _reason_category(reason: str) -> str:
    text = reason.lower()
    if "duplicate" in text: return "Duplicate listings"
    if "attendance" in text: return "Below/uncertain attendance"
    if "opportunity" in text: return "Below opportunity threshold"
    if "outside" in text: return "Outside configured market"
    return "Missing or conflicting data"


def _summary(schedule):
    selected = schedule["selected"]
    if not selected: return {"best_day": "No recommended day", "best_window": "Skip / insufficient evidence", "confidence": "Low"}
    best = max(selected, key=lambda item: (item.opportunity_score, item.confidence_score))
    windows = best.demand_windows
    return {"best_day": best.event.start_datetime.strftime("%A"), "best_window": f"{min(w.start for w in windows):%-I:%M %p}–{max(w.end for w in windows):%-I:%M %p %Z}", "confidence": f"{best.confidence_score}/100"}


def render_reports(week_start, opportunities, schedule, errors, output_dir: Path, feature_statuses=None, maximum_review_events=5, planned_conditions=None) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_statuses = feature_statuses or {"airport": "not_implemented", "traffic": "not_configured", "weather": "no_data_found"}
    top = sorted((o for o in opportunities if not o.suppressed), key=lambda o: (o.opportunity_score, o.confidence_score), reverse=True)[:5]
    suppressed = [o for o in opportunities if o.suppressed]
    review = sorted((o for o in suppressed if o.review_reasons), key=lambda o: o.opportunity_score, reverse=True)[:maximum_review_events]
    rejection_counts = Counter(_reason_category(reason) for o in suppressed for reason in (o.suppression_reasons or ["Missing or conflicting data"]))
    duplicates = sum(o.event.duplicate_count for o in opportunities)
    venue_conflicts = sum("venue_address" in o.event.conflicting_fields or "venue_name" in o.event.conflicting_fields for o in opportunities)
    weak_attendance = sum(o.event.attendance_basis in ("venue_capacity_only", "unknown") for o in opportunities)
    generated = datetime.now(timezone.utc)
    summary = _summary(schedule)
    lines = ["DRIVER DISPATCH INTELLIGENCE", "Independent decision support; not affiliated with Uber or Lyft; no guaranteed demand or surge claims.", f"Week of {week_start}", "Market: configured Utah operating areas", f"Generated: {generated:%Y-%m-%d %H:%M UTC}", "Data freshness: source timestamps and failures are reflected in confidence.", "", "WEEKLY SUMMARY", f"Best day: {summary['best_day']}", f"Best shift: {summary['best_window']}", f"Recommended weekly hours: {schedule['total_hours']} ({schedule['hour_calculation']})", f"Overall confidence: {summary['confidence']}", "", "SEVEN-DAY PLAN", "RECOMMENDED WEEKLY DRIVE PLAN"]
    for plan in schedule["plans"]:
        lines += ["", plan["day"].upper(), plan["status"]]
        if plan["primary"]:
            item = plan["primary"]
            if plan.get("start"): lines.append(f"Shift: {plan['start']:%-I:%M %p}–{plan['end']:%-I:%M %p %Z} | {plan['hours']} non-overlapping hours")
            lines += [f"Primary: {item.event.name}", f"Score: {item.opportunity_score}/100 | Confidence: {item.confidence_score}/100", f"Staging: {item.staging_guidance}", f"Reason: {plan['reason']}"]
            if plan["secondary"]: lines.append("Secondary: " + ", ".join(o.event.name for o in plan["secondary"]))
            lines.append("Expected transition: " + plan.get("transition", "Remain in the primary event area"))
            if plan["risks"]: lines.append("Risks: " + "; ".join(plan["risks"][:3]))
        else: lines.append(f"Skip — {plan['reason']}")
    lines += ["", "TOP OPPORTUNITIES"]
    for rank, o in enumerate(top, 1):
        event = o.event
        lines += ["", f"{rank}. {event.name}", f"When: {_fmt(event.start_datetime)}", f"Where: {_location(event)}", f"Opportunity / event demand score: {o.event_demand_score}/100 | Confidence {o.confidence_score}/100", "Mobility feasibility: Requires a pre-shift traffic check", "Final driver value status: Not determined from weekly demand alone", f"Attendance: {event.estimated_attendance_low or 'unknown'}–{event.estimated_attendance_high or 'unknown'} (basis: {event.attendance_basis}; capacity: {event.venue_capacity or 'unknown'})"]
        lines += [f"Drive for {w.kind}: {w.start:%-I:%M %p}–{w.end:%-I:%M %p %Z}" for w in o.demand_windows]
        lines += [f"Staging: {o.staging_guidance}", *[f"- {reason}" for reason in o.reasons[:6]]]
    if not top: lines.append("No event passed all recommendation gates.")
    lines += ["", "WEATHER SUMMARY"]
    weather_items = [o for o in top if o.event.weather]
    for o in weather_items:
        w = o.event.weather
        lines.append(f"- {o.event.name}: {w.get('temperature', '?')}°{w.get('temperature_unit', 'F')}, precipitation {w.get('precipitation_probability', 'unknown')}%, wind {w.get('wind_speed', 'unknown')}; demand {o.score_components.get('weather_demand', 0):+g}, safety {o.score_components.get('weather_safety', 0):+g}; {w.get('short_forecast', 'forecast')}")
        lines.append(f"  Severe alerts: {', '.join(w.get('severe_alerts', [])) or 'none'}; snow/ice risk: {w.get('snow_ice_risk', 'unknown')}; outdoor cancellation risk: {w.get('outdoor_cancellation_risk', 'unknown')}; forecast freshness: {w.get('forecast_generated_at', 'not supplied')}")
    if not weather_items: lines.append(STATUS_LABELS.get(feature_statuses.get("weather", "no_data_found"), "No forecast available"))
    lines += ["", "PLANNED MOBILITY CONDITIONS", "Construction and long-running conditions only; current traffic is not projected across the week."]
    for incident in (planned_conditions or [])[:20]:
        timestamp = incident.last_updated or incident.reported_time or incident.start_time
        lines.append(f"- {incident.category.replace('_', ' ').title()}: {incident.description} | {incident.roadway_name or 'roadway unspecified'} | source timestamp: {timestamp.isoformat() if timestamp else 'not supplied'}")
    if not planned_conditions: lines.append("No planned UDOT conditions available; verify before driving.")
    lines += ["", "AIRPORT / TRAFFIC / OPTIONAL INTELLIGENCE"]
    for feature in ("airport", "weather", "traffic"):
        lines.append(f"{feature.title()} intelligence: {STATUS_LABELS.get(feature_statuses.get(feature, 'not_configured'), feature_statuses.get(feature, 'Not configured'))}.")
    lines += ["", "VERIFY BEFORE DRIVING"]
    lines.extend(f"- {o.event.name}: {'; '.join(o.review_reasons[:3])}" for o in review)
    if not review: lines.append("No meaningful manual-review items.")
    lines += ["", "REJECTION SUMMARY", f"Rejected events: {len(suppressed)}", "Reasons:"]
    lines.extend(f"- {key}: {value}" for key, value in rejection_counts.most_common())
    lines += ["", "DATA QUALITY SUMMARY", f"Duplicates merged: {duplicates}", f"Venue conflicts fixed: {venue_conflicts}", f"Events with low-confidence attendance: {weak_attendance}", f"Source failures: {len(errors)}"]
    text = "\n".join(lines)
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape(["html"]))
    html = env.get_template("weekly_report.html.j2").render(report_text=text)
    stem = f"weekly-{week_start.isoformat()}"
    html_path, text_path = output_dir / f"{stem}.html", output_dir / f"{stem}.txt"
    html_path.write_text(html, encoding="utf-8"); text_path.write_text(text, encoding="utf-8")
    return html_path, text_path
