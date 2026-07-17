from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from driver_dispatch.database import Repository
from driver_dispatch.enrichment import enrich_venue, estimate_attendance
from driver_dispatch.enrichment.weather_enricher import enrich_weather
from driver_dispatch.normalization import deduplicate, normalize_event
from driver_dispatch.planning import build_schedule
from driver_dispatch.reports import render_reports
from driver_dispatch.scoring import score_event
from driver_dispatch.scoring.nearby_events import assign_nearby_events
from driver_dispatch.validation import validation_failures
from driver_dispatch.sources import ManualEventSource, SeatGeekSource, TicketmasterSource
from driver_dispatch.sources.holidays import HolidaySource
from driver_dispatch.sources.nws_weather import NWSWeatherSource
from driver_dispatch.mobility import MobilityService

log = logging.getLogger(__name__)


class DispatchService:
    def __init__(self, settings):
        self.settings = settings
        self.repo = Repository(settings.path(settings.app.database_path)); self.repo.migrate()
        cache = settings.path(settings.app.cache_dir)
        self.sources = [ManualEventSource(settings.path(settings.app.manual_events_file)), HolidaySource(settings.holidays, ZoneInfo(settings.app.timezone)), TicketmasterSource(cache, settings.locations), SeatGeekSource(cache, settings.locations)]
        self.weather = NWSWeatherSource(cache)
        self.mobility = MobilityService(settings, self.repo)

    def range(self, start=None, days=None):
        zone = ZoneInfo(self.settings.app.timezone)
        start = start or datetime.now(zone)
        return start, start + timedelta(days=days or self.settings.app.report_days_ahead)

    def collect(self, start=None, end=None, include_weather=False):
        start, default_end = self.range(start); end = end or default_end
        candidates, errors = [], []
        for source in self.sources:
            try:
                found = source.collect(start, end); candidates.extend(found)
                log.info("source_collected", extra={"source": source.name, "count": len(found)})
            except Exception as exc:
                error = {"source": source.name, "message": str(exc)}; errors.append(error)
                self.repo.record_error(source.name, str(exc)); log.warning("source_failed: %s: %s", source.name, exc)
        normalized = [estimate_attendance(enrich_venue(normalize_event(e, self.settings.app.timezone), self.settings.venues)) for e in candidates]
        events, uncertain = deduplicate(normalized)
        assign_nearby_events(events, self.settings.app.nearby_radius_miles, self.settings.app.nearby_minimum_attendance, self.settings.app.nearby_radius_by_venue_type)
        if include_weather:
            for event in events:
                if event.latitude is None or not event.start_datetime: continue
                try: enrich_weather(event, self.weather)
                except Exception as exc:
                    errors.append({"source": "nws", "message": str(exc)}); self.repo.record_error("nws", str(exc))
        self.repo.save_events(events)
        return events, errors, uncertain

    def score(self, events):
        output = []
        for event in events:
            item = score_event(event, self.settings)
            failures = validation_failures(event, self.settings)
            if failures:
                item.suppressed = True
                item.suppression_reasons.extend(reason for reason in failures if reason not in item.suppression_reasons)
                item.review_reasons.extend(reason for reason in failures if reason not in item.review_reasons)
            output.append(item)
        return sorted(output, key=lambda item: item.opportunity_score, reverse=True)

    def weekly_report(self, start=None, refresh=True):
        start, end = self.range(start)
        if refresh: events, errors, uncertain = self.collect(start, end, include_weather=False)
        else: events, errors, uncertain = self.repo.events_between(start, end), [], []
        opportunities = self.score(events)
        schedule = build_schedule(opportunities, self.settings.app.maximum_weekly_hours, start.date(), self.settings.app.maximum_daily_hours, self.settings.app.adjacent_window_minutes)
        # Weather is decision intelligence for recommended windows, not a reason to make
        # hundreds of forecast requests for already-rejected events.
        weather_attempted = set()
        if refresh:
            for _ in range(2):
                pending = [item.event for item in schedule["selected"] if item.event.id not in weather_attempted and item.event.latitude is not None]
                if not pending: break
                for event in pending:
                    weather_attempted.add(event.id)
                    try: enrich_weather(event, self.weather)
                    except Exception as exc:
                        errors.append({"source": "nws", "message": str(exc)}); self.repo.record_error("nws", str(exc))
                opportunities = self.score(events)
                schedule = build_schedule(opportunities, self.settings.app.maximum_weekly_hours, start.date(), self.settings.app.maximum_daily_hours, self.settings.app.adjacent_window_minutes)
            self.repo.save_events(events)
        feature_statuses = dict(self.settings.feature_statuses)
        if any(error["source"] == "nws" for error in errors): feature_statuses["weather"] = "source_failed"
        elif not any(event.weather for event in events): feature_statuses["weather"] = "no_data_found" if feature_statuses.get("weather") == "available" else feature_statuses.get("weather", "not_configured")
        planned_conditions = []
        try:
            incidents = self.mobility.udot.incidents()
            planned_conditions = [incident for incident in incidents if incident.planned or incident.category in ("construction", "closure")]
            feature_statuses["traffic"] = "available"
        except Exception as exc:
            errors.append({"source":"udot", "message":str(exc)}); feature_statuses["traffic"] = "not_configured" if not self.settings.traffic.udot_api_key else "source_failed"
        paths = render_reports(start.date(), opportunities, schedule, errors, self.settings.path(self.settings.app.report_dir), feature_statuses, self.settings.app.maximum_review_events, planned_conditions)
        self.repo.save_report(start.date(), *paths, opportunities)
        return {"events": events, "opportunities": opportunities, "schedule": schedule, "errors": errors, "uncertain_duplicates": uncertain, "paths": paths}
