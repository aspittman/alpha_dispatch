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
from driver_dispatch.sources import ManualEventSource, SeatGeekSource, TicketmasterSource
from driver_dispatch.sources.holidays import HolidaySource
from driver_dispatch.sources.nws_weather import NWSWeatherSource

log = logging.getLogger(__name__)


class DispatchService:
    def __init__(self, settings):
        self.settings = settings
        self.repo = Repository(settings.path(settings.app.database_path)); self.repo.migrate()
        cache = settings.path(settings.app.cache_dir)
        self.sources = [ManualEventSource(settings.path(settings.app.manual_events_file)), HolidaySource(settings.holidays, ZoneInfo(settings.app.timezone)), TicketmasterSource(cache, settings.locations), SeatGeekSource(cache, settings.locations)]
        self.weather = NWSWeatherSource(cache)

    def range(self, start=None, days=None):
        zone = ZoneInfo(self.settings.app.timezone)
        start = start or datetime.now(zone)
        return start, start + timedelta(days=days or self.settings.app.report_days_ahead)

    def collect(self, start=None, end=None, include_weather=True):
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
            overlap = sum(1 for other in events if other is not event and event.start_datetime and other.start_datetime and abs((event.start_datetime - other.start_datetime).total_seconds()) <= 7200 and event.city and event.city == other.city)
            output.append(score_event(event, self.settings, overlap))
        return sorted(output, key=lambda item: item.opportunity_score, reverse=True)

    def weekly_report(self, start=None, refresh=True):
        start, end = self.range(start)
        if refresh: events, errors, uncertain = self.collect(start, end)
        else: events, errors, uncertain = self.repo.events_between(start, end), [], []
        opportunities = self.score(events)
        schedule = build_schedule(opportunities, self.settings.app.maximum_weekly_hours)
        paths = render_reports(start.date(), opportunities, schedule, errors, self.settings.path(self.settings.app.report_dir))
        self.repo.save_report(start.date(), *paths, opportunities)
        return {"events": events, "opportunities": opportunities, "schedule": schedule, "errors": errors, "uncertain_duplicates": uncertain, "paths": paths}
