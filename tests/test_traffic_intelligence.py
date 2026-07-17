from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx

from driver_dispatch.adapters.google_routes import FIELD_MASK, GoogleQuotaExceeded, GoogleRoutesAdapter, duration_seconds, severity
from driver_dispatch.adapters.udot_traffic import UdotTrafficAdapter, normalize_udot
from driver_dispatch.config.settings import OperatingZone
from driver_dispatch.mobility import classify, relevant_incidents
from driver_dispatch.models import RouteMetric, TrafficIncident
from driver_dispatch.traffic_cache import JsonCache


class Response:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


class Client:
    def __init__(self, get_data=None, post_data=None): self.get_data=get_data or []; self.post_data=post_data or []; self.calls=[]
    def get(self, url, **kwargs): self.calls.append((url, kwargs)); return Response(self.get_data.pop(0))
    def post(self, url, **kwargs): self.calls.append((url, kwargs)); return Response(self.post_data)


def traffic_settings(**overrides):
    values = dict(udot_api_key="secret", udot_base_url="https://udot.test/api/v2", udot_enabled=True, udot_cache_minutes=5, google_api_key="secret", google_base_url="https://routes.test", google_enabled=True, google_routing_preference="TRAFFIC_AWARE", google_cache_minutes=5, google_max_daily_requests=50, google_max_destinations_per_check=10, request_timeout_seconds=1)
    values.update(overrides); return SimpleNamespace(**values)


def test_udot_event_alert_and_unix_normalization(tmp_path):
    event = normalize_udot({"Id":"1","EventType":"Crash","Description":"Crash NB","RoadwayName":"I-15","Latitude":40.3,"Longitude":-111.7,"LastUpdated":1_700_000_000})
    alert = normalize_udot({"AlertId":"2","Headline":"Road closed","Updated":1_700_000_000_000}, "alert")
    assert event.category == "crash" and event.last_updated.tzinfo
    assert alert.category == "closure" and alert.raw_source_reference["kind"] == "alert"


def test_udot_key_parameter_cache_and_throttle_hook(tmp_path):
    client = Client(get_data=[[{"Id":"1","Description":"Work","EventType":"Construction"}], []])
    adapter = UdotTrafficAdapter(traffic_settings(), JsonCache(tmp_path), client=client, sleep=lambda _: None)
    first = adapter.incidents(); second = adapter.incidents()
    assert first[0].planned and len(client.calls) == 2 and adapter.stats["cache_hits"] == 2
    assert client.calls[0][1]["params"] == {"key":"secret"}


def test_google_request_mask_format_parse_and_cache(tmp_path):
    client = Client(post_data=[{"destinationIndex":0,"condition":"ROUTE_EXISTS","distanceMeters":16093.44,"duration":"1200s","staticDuration":"900s"}])
    adapter = GoogleRoutesAdapter(traffic_settings(), JsonCache(tmp_path), {"clear":{"maximum_delay_minutes":3,"maximum_multiplier":1.1},"minor":{"maximum_delay_minutes":8,"maximum_multiplier":1.25},"moderate":{"maximum_delay_minutes":15,"maximum_multiplier":1.5},"heavy":{"maximum_delay_minutes":30,"maximum_multiplier":2}}, client)
    result = adapter.matrix((40.2,-111.7), [("lehi",40.39,-111.85)])
    request = client.calls[0][1]
    assert request["json"]["travelMode"] == "DRIVE" and request["json"]["routingPreference"] == "TRAFFIC_AWARE"
    assert request["headers"]["X-Goog-FieldMask"] == FIELD_MASK and "polyline" not in FIELD_MASK.lower()
    assert result["lehi"].distance_miles == 10 and result["lehi"].delay_minutes == 5
    adapter.matrix((40.2,-111.7), [("lehi",40.39,-111.85)])
    assert len(client.calls) == 1


def test_duration_severity_and_zero_safety():
    thresholds={"clear":{"maximum_delay_minutes":3,"maximum_multiplier":1.1},"minor":{"maximum_delay_minutes":8,"maximum_multiplier":1.25},"moderate":{"maximum_delay_minutes":15,"maximum_multiplier":1.5},"heavy":{"maximum_delay_minutes":30,"maximum_multiplier":2}}
    assert duration_seconds("90.5s") == 90.5
    assert severity(18, 1.2, thresholds) == "heavy"
    assert severity(None, None, thresholds) == "unavailable"


def test_relevance_includes_nearby_excludes_unrelated():
    zone = OperatingZone(name="provo", latitude=40.2338, longitude=-111.6585, radius_miles=5)
    near = TrafficIncident(source_id="1", description="near", latitude=40.24, longitude=-111.66)
    far = TrafficIncident(source_id="2", description="far", latitude=41.0, longitude=-112.0, roadway_name="I-80")
    assert [x.source_id for x in relevant_incidents([near,far], (40.29,-111.69), zone, [])] == ["1"]


def test_classification_drift_and_late_shift(settings):
    settings.zones = {}; settings.traffic.planned_shift_end=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(); settings.traffic.drift_penalty_increase_last_90_minutes=True
    zone=OperatingZone(name="lehi",latitude=40.39,longitude=-111.85,priority="conditional",directional_drift_risk=8,user_penalty=8)
    route=RouteMetric(origin_name="orem",destination_name="lehi",live_duration_minutes=25,static_duration_minutes=23,delay_minutes=2,traffic_multiplier=1.08,distance_miles=20,traffic_severity="clear",fetched_at=datetime.now(timezone.utc))
    category, penalty, _ = classify(zone, route, [], settings)
    assert category == "ACCEPTABLE" and penalty == 24
    route.traffic_severity="heavy"; assert classify(zone, route, [], settings)[0] == "AVOID"


def test_google_daily_guard(tmp_path):
    adapter=GoogleRoutesAdapter(traffic_settings(google_max_daily_requests=0), JsonCache(tmp_path), {}, Client(post_data=[]))
    try: adapter.matrix((1,2), [("x",3,4)])
    except GoogleQuotaExceeded as exc: assert "daily" in str(exc)
    else: raise AssertionError("quota guard did not stop request")


def test_cache_stale_handling(tmp_path):
    cache=JsonCache(tmp_path); cache.set("x","y",{"ok":True})
    path=cache._path("x","y"); text=path.read_text().replace(datetime.now(timezone.utc).date().isoformat(), "2000-01-01") ; path.write_text(text)
    assert cache.get("x","y",5) is None
    assert cache.get("x","y",5,allow_stale=True)[2] is True


def test_secrets_not_in_adapter_errors(tmp_path):
    class Broken(Client):
        def get(self, *args, **kwargs): raise httpx.ConnectError("offline")
    adapter=UdotTrafficAdapter(traffic_settings(),JsonCache(tmp_path),Broken(),sleep=lambda _:None)
    try: adapter.incidents()
    except RuntimeError as exc: assert "secret" not in str(exc)
