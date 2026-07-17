from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from driver_dispatch.adapters import GoogleRoutesAdapter, UdotTrafficAdapter
from driver_dispatch.api_usage import UsageLedger
from driver_dispatch.models import TrafficIncident, ZoneRecommendation
from driver_dispatch.scoring import score_event
from driver_dispatch.traffic_cache import JsonCache


def miles_between(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b)); dlat = lat2-lat1; dlon = lon2-lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def _safe_error(exc, *secrets):
    text = str(exc)
    for secret in secrets:
        if secret: text = text.replace(secret, "[REDACTED]")
    return text


def relevant_incidents(incidents: list[TrafficIncident], origin, zone, corridors, now=None):
    now = now or datetime.now(timezone.utc); matched = []
    aliases = []
    for corridor in corridors:
        if zone.name in corridor.get("zones", []): aliases.extend(corridor.get("aliases", []))
    for incident in incidents:
        if not incident.active or (incident.end_time and incident.end_time < now): continue
        close = incident.latitude is not None and incident.longitude is not None and miles_between((incident.latitude, incident.longitude), (zone.latitude, zone.longitude)) <= zone.radius_miles + 2
        road = bool(incident.roadway_name and any(alias.lower() in incident.roadway_name.lower() for alias in aliases))
        # A roadway match is only accepted for a configured origin-to-zone corridor.
        if close or road:
            copy = incident.model_copy(deep=True); copy.affected_zones = sorted(set(copy.affected_zones + [zone.name])); matched.append(copy)
    return matched


def _late_shift(settings, now):
    value = settings.traffic.planned_shift_end
    if not value or not settings.traffic.drift_penalty_increase_last_90_minutes: return False
    try:
        end = datetime.fromisoformat(value)
        if end.tzinfo is None: end = end.replace(tzinfo=now.tzinfo)
        return 0 <= (end - now).total_seconds() <= 5400
    except ValueError: return False


def classify(zone, route, incidents, settings, now=None):
    now = now or datetime.now(timezone.utc)
    drift = zone.directional_drift_risk * (2 if _late_shift(settings, now) else 1)
    penalty = zone.user_penalty + drift
    if route is None: return "UNAVAILABLE", penalty, ["Current route duration unavailable"]
    closure = any(i.category == "closure" and i.active for i in incidents)
    if closure or route.traffic_severity in ("heavy", "severe"):
        reason = "Active relevant closure" if closure else f"{route.traffic_severity.title()} measured traffic delay"
        return "AVOID", penalty, [reason]
    if zone.priority == "discouraged": return "AVOID", penalty, ["Distant/discouraged zone without a measured advantage"]
    if route.distance_miles is not None and route.distance_miles > settings.app.maximum_driving_distance_miles:
        return "AVOID", penalty, ["Positioning distance exceeds configured preference"]
    if zone.priority == "preferred" and route.traffic_severity in ("clear", "minor", "moderate"):
        return "PREFER", penalty, ["Preferred local zone with operational travel conditions"]
    return "ACCEPTABLE", penalty, ["Operational, but not clearly better than preferred local zones"]


class MobilityService:
    def __init__(self, settings, repo, google=None, udot=None):
        self.settings, self.repo = settings, repo
        cache = JsonCache(settings.path(settings.app.cache_dir) / "mobility")
        self.ledger = UsageLedger(settings.path(settings.app.database_path), settings.traffic)
        thresholds = settings.mobility.get("traffic_thresholds") or {"clear":{"maximum_delay_minutes":3,"maximum_multiplier":1.1},"minor":{"maximum_delay_minutes":8,"maximum_multiplier":1.25},"moderate":{"maximum_delay_minutes":15,"maximum_multiplier":1.5},"heavy":{"maximum_delay_minutes":30,"maximum_multiplier":2}}
        self.google = google or GoogleRoutesAdapter(settings.traffic, cache, thresholds, ledger=self.ledger)
        self.udot = udot or UdotTrafficAdapter(settings.traffic, cache, ledger=self.ledger)

    def run(self, mode, origin_zone="orem", latitude=None, longitude=None, include_distant=False, include_northern=False, force=False, confirmed=False, driving=False):
        now = datetime.now(timezone.utc); errors = []
        self.google.stats = {"api_calls":0,"cache_hits":0,"elements":0}; self.udot.stats = {"api_calls":0,"cache_hits":0}
        if force and driving: raise ValueError("Force refresh is unavailable while driving; use it only while safely parked")
        if latitude is not None and longitude is not None: origin, origin_name = (latitude, longitude), "current coordinates"
        else:
            zone = self.settings.zones.get(origin_zone)
            if not zone: raise ValueError(f"Unknown current zone: {origin_zone}")
            origin, origin_name = (zone.latitude, zone.longitude), origin_zone
        try: incidents = self.udot.incidents()
        except Exception as exc: incidents = []; errors.append({"source":"udot", "message":_safe_error(exc, self.settings.traffic.udot_api_key)})
        core = [n for n in ("orem","provo","vineyard","lindon","springville","spanish_fork") if n in self.settings.zones]
        northern = [n for n in ("pleasant_grove","american_fork","lehi","saratoga_springs") if n in self.settings.zones]
        distant = [n for n in ("draper","sandy","salt_lake_city","west_valley_city") if n in self.settings.zones]
        names, destination_reasons = list(core), {n:"core local destination" for n in core}
        near_north = origin[0] >= 40.35
        if include_northern or near_north or not self.settings.traffic.low_usage_mode:
            for n in northern: names.append(n); destination_reasons[n] = "explicit northern selection" if include_northern else "origin is in northern Utah County" if near_north else "standard mode configured"
        if include_distant or (not self.settings.traffic.low_usage_mode and self.settings.traffic.include_distant_zones_by_default) or origin[0] > 40.5:
            for n in distant: names.append(n); destination_reasons[n] = "explicit distant selection" if include_distant else "origin is near distant zones"
        names = list(dict.fromkeys(names))[:self.settings.traffic.google_max_elements_per_refresh]
        destinations = [(name, self.settings.zones[name].latitude, self.settings.zones[name].longitude) for name in names]
        try: routes = self.google.matrix(origin, destinations, mode, force=force, confirmed=confirmed)
        except Exception as exc: routes = {}; errors.append({"source":"google", "message":_safe_error(exc, self.settings.traffic.google_api_key)})
        recommendations = []
        for name in names:
            zone = self.settings.zones[name]; route = routes.get(name)
            relevant = relevant_incidents(incidents, origin, zone, self.settings.mobility.get("corridors", []), now)
            category, penalty, reasons = classify(zone, route, relevant, self.settings, now)
            if relevant and route and route.delay_minutes is not None and route.delay_minutes <= 3: reasons.append("Incident present, but current route impact appears limited")
            if route and route.delay_minutes and route.delay_minutes > 3 and not relevant: reasons.append("Cause may be general congestion or an incident absent from UDOT")
            if drift := zone.directional_drift_risk: reasons.append(f"User-observed northbound drift preference penalty: {drift}")
            recommendations.append(ZoneRecommendation(zone=name, classification=category, route=route, incidents=relevant, reasons=reasons, preference_penalty=penalty))
        previous = self.repo.latest_traffic_run("live_refresh") if mode == "live_refresh" else None
        changes = self._changes(previous, recommendations)
        event_impacts = self._event_impacts(now, recommendations, origin)
        usage = self.ledger.usage()
        static_distances = {name:self.repo.latest_static_distance(name) for name in names}
        result = {"mode":mode,"generated_at":now,"origin_name":origin_name,"origin":{"latitude":origin[0],"longitude":origin[1]},"recommendations":recommendations,"incidents":incidents,"errors":errors,"changes":changes,"event_impacts":event_impacts,"destination_reasons":destination_reasons,"selected_destination_count":len(names),"static_distances":static_distances,"stats":{"google":dict(self.google.stats),"udot":dict(self.udot.stats),"google_remaining":self.google.remaining,"usage":usage}}
        self.repo.save_traffic_run(result)
        return result

    def _event_impacts(self, now, recommendations, origin):
        by_zone = {item.zone:item for item in recommendations}
        try: events = self.repo.events_between(now, now.replace(hour=23, minute=59, second=59) + timedelta(days=2))
        except Exception: return []
        impacts = []
        for event in events:
            if event.latitude is None or event.longitude is None: continue
            zone_name, distance = min(((name, miles_between((event.latitude,event.longitude),(z.latitude,z.longitude))) for name,z in self.settings.zones.items()), key=lambda x:x[1])
            rec = by_zone.get(zone_name)
            if not rec or distance > self.settings.zones[zone_name].radius_miles + 3: continue
            demand = score_event(event, self.settings).opportunity_score
            status = "operational" if rec.classification in ("PREFER","ACCEPTABLE") else "do not travel solely for this event" if rec.classification == "AVOID" else "unavailable"
            impacts.append({"name":event.name,"zone":zone_name,"event_demand_score":demand,"mobility_feasibility":rec.classification.lower(),"final_driver_value_status":status,"round_trip_positioning_miles":round(rec.route.distance_miles*2,1) if rec.route and rec.route.distance_miles is not None else None,"delay_minutes":rec.route.delay_minutes if rec.route else None,"relevant_incidents":len(rec.incidents)})
        return sorted(impacts, key=lambda x:x["event_demand_score"], reverse=True)[:5]

    @staticmethod
    def _changes(previous, recommendations):
        if not previous: return ["No previous live check is available for comparison."]
        old = {x["zone"]: x for x in previous.get("recommendations", [])}; changes = []
        for item in recommendations:
            before = old.get(item.zone)
            if before and before.get("classification") != item.classification: changes.append(f"{item.zone.replace('_',' ').title()} changed from {before['classification'].lower()} to {item.classification.lower()}.")
            elif before and item.route and before.get("route") and before["route"].get("delay_minutes") is not None:
                delta = item.route.delay_minutes - before["route"]["delay_minutes"]
                if abs(delta) >= 2: changes.append(f"{item.zone.replace('_',' ').title()} delay {'increased' if delta > 0 else 'improved'} by {abs(delta):.0f} minutes.")
        return changes or ["No material zone-level changes since the previous check."]
