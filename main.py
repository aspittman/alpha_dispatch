from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from driver_dispatch.config import load_settings
from driver_dispatch.history import session_from_args
from driver_dispatch.reports.email_report import send_report
from driver_dispatch.service import DispatchService
from driver_dispatch.reports.mobility_report import render_mobility


def dt(value: str): return datetime.fromisoformat(value)


def parser():
    p = argparse.ArgumentParser(prog="Driver Dispatch Intelligence", description="Independent, explainable rideshare opportunity planning; not affiliated with Uber or Lyft.")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--mode", choices=["weekly", "pre_shift", "live_refresh"])
    p.add_argument("--current-zone", default="orem")
    p.add_argument("--latitude", type=float); p.add_argument("--longitude", type=float)
    p.add_argument("--include-distant-zones", action="store_true")
    sub = p.add_subparsers(dest="command", required=False)
    weekly = sub.add_parser("weekly-report"); weekly.add_argument("--no-refresh", action="store_true"); weekly.add_argument("--email", action="store_true")
    sub.add_parser("collect-events"); sub.add_parser("score-events"); show = sub.add_parser("show-top"); show.add_argument("--limit", type=int, default=10)
    backfill = sub.add_parser("backfill-week"); backfill.add_argument("date", help="Week start YYYY-MM-DD")
    sub.add_parser("test-sources")
    session = sub.add_parser("log-session"); session.add_argument("--start", required=True, type=dt); session.add_argument("--end", required=True, type=dt); session.add_argument("--gross", required=True, type=float); session.add_argument("--miles", required=True, type=float); session.add_argument("--tips", type=float, default=0); session.add_argument("--bonuses", type=float, default=0); session.add_argument("--fuel", type=float, default=0); session.add_argument("--trips", type=int, default=0); session.add_argument("--starting-area"); session.add_argument("--ending-area"); session.add_argument("--event"); session.add_argument("--waiting", type=float); session.add_argument("--deadhead", type=float); session.add_argument("--notes")
    return p


def main():
    args = parser().parse_args(); logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}')
    settings = load_settings(); service = DispatchService(settings); zone = ZoneInfo(settings.app.timezone)
    if args.mode in ("pre_shift", "live_refresh"):
        if (args.latitude is None) != (args.longitude is None): raise SystemExit("--latitude and --longitude must be supplied together")
        result = service.mobility.run(args.mode, args.current_zone, args.latitude, args.longitude, args.include_distant_zones)
        report = render_mobility(result); output = settings.path(settings.app.report_dir); output.mkdir(parents=True, exist_ok=True)
        path = output / f"{args.mode}-{result['generated_at'].strftime('%Y%m%d-%H%M%S')}.txt"; path.write_text(report, encoding="utf-8")
        print(report); print(f"\nSaved: {path}")
    elif args.command == "weekly-report" or args.mode == "weekly":
        result = service.weekly_report(refresh=not getattr(args, "no_refresh", False)); print(f"HTML: {result['paths'][0]}\nText: {result['paths'][1]}\nEvents: {len(result['events'])}; source errors: {len(result['errors'])}")
        if getattr(args, "email", False):
            if not settings.app.email_address: raise SystemExit("Configure DISPATCH_EMAIL_TO before using --email")
            send_report(settings.app.email_address, *result["paths"]); print("Email sent")
    elif args.command == "collect-events":
        events, errors, uncertain = service.collect(); print(f"Collected {len(events)} events; {len(errors)} source errors; {len(uncertain)} uncertain duplicate pairs")
    elif args.command in ("score-events", "show-top"):
        start, end = service.range(); scored = service.score(service.repo.events_between(start, end)); limit = args.limit if args.command == "show-top" else len(scored)
        for item in scored[:limit]: print(f"{item.opportunity_score:5.1f} opportunity | {item.confidence_score:5.1f} confidence | {item.event.name} | {'SUPPRESSED' if item.suppressed else 'candidate'}")
    elif args.command == "backfill-week":
        start = datetime.fromisoformat(args.date).replace(tzinfo=zone); result = service.weekly_report(start); print(result["paths"][0])
    elif args.command == "test-sources":
        start, end = service.range()
        for source in service.sources:
            try: print(f"{source.name}: OK ({len(source.collect(start, end))} events)")
            except Exception as exc: print(f"{source.name}: FAILED ({exc})")
    elif args.command == "log-session":
        session = session_from_args(args); ident = service.repo.save_session(session); print(f"Saved session {ident}\n{json.dumps(session.metrics(), indent=2)}")
    else: parser().print_help()


if __name__ == "__main__": main()
