from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def _summary(schedule):
    selected = schedule["selected"]
    if not selected: return {"best_day": "No recommended day", "best_window": "Skip / insufficient evidence"}
    best = selected[0]
    windows = best.demand_windows
    return {"best_day": best.event.start_datetime.strftime("%A"), "best_window": f"{min(w.start for w in windows):%-I:%M %p}–{max(w.end for w in windows):%-I:%M %p}"}


def render_reports(week_start, opportunities, schedule, errors, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    top = sorted((o for o in opportunities if not o.suppressed), key=lambda o: o.opportunity_score, reverse=True)[:5]
    suppressed = [o for o in opportunities if o.suppressed]
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["fmt"] = lambda value: value.strftime("%a %b %-d, %-I:%M %p") if value else "Time unknown"
    env.filters["time"] = lambda value: value.strftime("%-I:%M %p")
    env.filters["window_range"] = lambda windows: f"{min(w.start for w in windows):%-I:%M %p}–{max(w.end for w in windows):%-I:%M %p}"
    context = {"week_start": week_start, "summary": _summary(schedule), "top": top, "suppressed": suppressed, "schedule": schedule, "errors": errors}
    html = env.get_template("weekly_report.html.j2").render(**context)
    lines = ["DRIVER DISPATCH INTELLIGENCE", "Independent; not affiliated with Uber or Lyft. No future surge pricing is claimed.", f"Week of {week_start}", f"Best day: {context['summary']['best_day']}", f"Best window: {context['summary']['best_window']}", f"Recommended total: {schedule['total_hours']} hours", "", "TOP OPPORTUNITIES"]
    for o in top:
        lines += [f"\n{o.event.name} — {o.event.venue_name or o.event.city or 'location unknown'}", f"Opportunity {o.opportunity_score}/100 | Confidence {o.confidence_score}/100", *[f"- {r}" for r in o.reasons[:5]], f"Staging: {o.staging_guidance}"]
    if not top: lines.append("No opportunity cleared configured thresholds; consider skipping.")
    if errors: lines += ["", "SOURCE ERRORS", *[f"- {e['source']}: {e['message']}" for e in errors]]
    lines += ["", "AIRPORT", "Airport intelligence is unavailable in V1.", "", "AVOID / VERIFY", *[f"- {o.event.name}: {'; '.join(o.suppression_reasons)}" for o in suppressed]]
    stem = f"weekly-{week_start.isoformat()}"
    html_path, text_path = output_dir / f"{stem}.html", output_dir / f"{stem}.txt"
    html_path.write_text(html, encoding="utf-8"); text_path.write_text("\n".join(lines), encoding="utf-8")
    return html_path, text_path

