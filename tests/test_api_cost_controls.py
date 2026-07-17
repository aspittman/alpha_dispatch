from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from driver_dispatch.adapters.google_routes import GoogleQuotaExceeded, GoogleRoutesAdapter
from driver_dispatch.api_usage import UsageLedger, UsageLimitExceeded, billing_buckets, effective_monthly_limit, matrix_elements
from driver_dispatch.config.settings import TrafficSettings
from driver_dispatch.config.settings import AppSettings, OperatingZone, Settings
from driver_dispatch.database import Repository
from driver_dispatch.mobility import MobilityService, _safe_error
from driver_dispatch.reports.mobility_report import render_mobility
from driver_dispatch.traffic_cache import JsonCache


THRESHOLDS = {name:{"maximum_delay_minutes":limit,"maximum_multiplier":mult} for name,limit,mult in (("clear",3,1.1),("minor",8,1.25),("moderate",15,1.5),("heavy",30,2))}


class Response:
    def raise_for_status(self): pass
    def json(self): return [{"destinationIndex":0,"condition":"ROUTE_EXISTS","duration":"60s","staticDuration":"60s"}]


class Client:
    def __init__(self, fail=False): self.calls=0; self.fail=fail
    def post(self, *args, **kwargs):
        self.calls += 1
        if self.fail: raise RuntimeError("offline; key=must-not-appear")
        return Response()


def setup(tmp_path, **overrides):
    values={"google_api_key":"test-key","google_base_url":"https://routes.test","google_max_monthly_elements":100}; values.update(overrides)
    cfg=TrafficSettings(**values)
    path=tmp_path/"usage.db"; repo=Repository(path); repo.migrate(); repo.connection.close()
    ledger=UsageLedger(path,cfg)
    return cfg,ledger,GoogleRoutesAdapter(cfg,JsonCache(tmp_path/"cache"),THRESHOLDS,Client(),ledger)


def test_matrix_element_math_and_normal_origin_rule(tmp_path):
    assert matrix_elements(1,8)==8 and matrix_elements(2,8)==16
    _,ledger,_=setup(tmp_path)
    with pytest.raises(UsageLimitExceeded,match="exactly one"): ledger.reserve_google(2,4)


def test_safety_percentage_and_explicit_cap():
    assert effective_monthly_limit(TrafficSettings(google_monthly_free_elements=5000,google_monthly_safety_percent=80))==4000
    assert effective_monthly_limit(TrafficSettings(google_monthly_free_elements=5000,google_max_monthly_elements=3500))==3500


def test_missing_limit_daily_and_monthly_are_preflight_blocks(tmp_path):
    cfg=TrafficSettings(google_api_key="x",google_monthly_free_elements=None,google_max_monthly_elements=None)
    path=tmp_path/"x.db"; repo=Repository(path); repo.migrate(); repo.connection.close(); ledger=UsageLedger(path,cfg)
    with pytest.raises(UsageLimitExceeded,match="not configured"): ledger.reserve_google(1,1)
    cfg,ledger,_=setup(tmp_path/"daily",google_max_daily_elements=1)
    ledger.reserve_google(1,1)
    with pytest.raises(UsageLimitExceeded,match="daily"): ledger.reserve_google(1,1)
    cfg,ledger,_=setup(tmp_path/"monthly",google_max_monthly_elements=1)
    ledger.reserve_google(1,1)
    with pytest.raises(UsageLimitExceeded,match="monthly"): ledger.reserve_google(1,1)


def test_cache_hit_uses_zero_elements_and_survives_restart(tmp_path):
    cfg,ledger,adapter=setup(tmp_path)
    destinations=[("orem",40.29,-111.69)]
    adapter.matrix((40.2,-111.7),destinations)
    before=ledger.usage()["google_month"]
    restarted=GoogleRoutesAdapter(cfg,JsonCache(tmp_path/"cache"),THRESHOLDS,Client(),UsageLedger(tmp_path/"usage.db",cfg))
    result=restarted.matrix((40.2,-111.7),destinations)
    assert result["orem"].cache_hit and restarted.ledger.usage()["google_month"]==before==1


def test_atomic_concurrent_reservations_cannot_bypass_cap(tmp_path):
    cfg,ledger,_=setup(tmp_path,google_max_daily_elements=1)
    def reserve():
        try: ledger.reserve_google(1,1); return True
        except UsageLimitExceeded: return False
    with ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(lambda _:reserve(),range(8)))
    assert results.count(True)==1 and ledger.usage()["google_today"]==1


def test_failure_after_reservation_is_conservatively_counted_and_redacted(tmp_path):
    cfg,ledger,_=setup(tmp_path)
    adapter=GoogleRoutesAdapter(cfg,JsonCache(tmp_path/"cache"),THRESHOLDS,Client(fail=True),ledger)
    with pytest.raises(RuntimeError) as caught: adapter.matrix((40,-111),[("x",41,-112)])
    assert "test-key" not in str(caught.value) and ledger.usage()["google_month"]==1


def test_force_refresh_confirmation_and_cooldown(tmp_path):
    cfg,ledger,adapter=setup(tmp_path)
    dest=[("orem",40.29,-111.69)]; adapter.matrix((40.2,-111.7),dest)
    with pytest.raises(GoogleQuotaExceeded,match="confirm"): adapter.matrix((40.2,-111.7),dest,force=True)
    adapter.matrix((40.2,-111.7),dest,force=True,confirmed=True)
    with pytest.raises(GoogleQuotaExceeded,match="cooldown"): adapter.matrix((40.2,-111.7),dest,force=True,confirmed=True)


def test_billing_month_reset_day_and_timezone_boundary():
    assert billing_buckets(datetime(2026,7,1,5,30,tzinfo=timezone.utc),"America/Denver",1)[0]=="2026-06-01"
    assert billing_buckets(datetime(2026,7,1,6,30,tzinfo=timezone.utc),"America/Denver",1)[0]=="2026-07-01"
    assert billing_buckets(datetime(2026,7,14,12,tzinfo=timezone.utc),"America/Denver",15)[0]=="2026-06-15"


def test_paid_overage_opt_in_is_explicit(tmp_path):
    _,ledger,_=setup(tmp_path,google_max_monthly_elements=1,google_allow_paid_overage=True)
    ledger.reserve_google(1,1); ledger.reserve_google(1,1)
    assert ledger.usage()["google_month"]==2


def test_secret_redaction():
    assert _safe_error(RuntimeError("header secret-key"), "secret-key") == "header [REDACTED]"


class FakeGoogle:
    def __init__(self): self.stats={}; self.destinations=[]; self.remaining=80
    def matrix(self, origin,destinations,mode,**kwargs): self.destinations=[x[0] for x in destinations]; return {}


class FakeUdot:
    def __init__(self): self.stats={}
    def incidents(self): return []


def test_low_usage_destination_trimming_and_udot_only_dashboard(tmp_path):
    names=("orem","provo","vineyard","lindon","springville","spanish_fork","pleasant_grove","american_fork","lehi","saratoga_springs","salt_lake_city","west_valley_city")
    zones={name:OperatingZone(name=name,latitude=40.2+i*.001,longitude=-111.7) for i,name in enumerate(names)}
    cfg=Settings(app=AppSettings(database_path=str(tmp_path/"dispatch.db"),cache_dir=str(tmp_path/"cache")),locations=[],zones=zones,traffic=TrafficSettings(google_max_monthly_elements=100,low_usage_mode=True))
    repo=Repository(tmp_path/"dispatch.db"); repo.migrate(); google=FakeGoogle(); service=MobilityService(cfg,repo,google=google,udot=FakeUdot())
    result=service.run("pre_shift","orem")
    assert google.destinations==list(names[:6]) and result["selected_destination_count"]==6
    text=render_mobility(result)
    assert "Google live duration: Unavailable" in text and "Google Routes today: 0 / 80 elements" in text and "UDOT Traffic: available" in text
