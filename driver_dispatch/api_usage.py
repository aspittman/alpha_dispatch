from __future__ import annotations

import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class UsageLimitExceeded(RuntimeError):
    """Raised before an external request when its reservation would exceed a cap."""


def matrix_elements(origin_count: int, destination_count: int) -> int:
    if origin_count < 1 or destination_count < 1:
        raise ValueError("Route Matrix requires at least one origin and one destination")
    return origin_count * destination_count


def effective_monthly_limit(settings) -> int | None:
    limits = []
    if settings.google_monthly_free_elements is not None:
        limits.append(math.floor(settings.google_monthly_free_elements * settings.google_monthly_safety_percent / 100))
    if settings.google_max_monthly_elements is not None:
        limits.append(settings.google_max_monthly_elements)
    return min(limits) if limits else None


def billing_buckets(now: datetime, timezone_name: str, reset_day: int) -> tuple[str, str]:
    local = now.astimezone(ZoneInfo(timezone_name))
    if not 1 <= reset_day <= 28:
        raise ValueError("GOOGLE_ROUTES_BILLING_RESET_DAY must be between 1 and 28")
    year, month = local.year, local.month
    if local.day < reset_day:
        month -= 1
        if month == 0: year, month = year - 1, 12
    return f"{year:04d}-{month:02d}-{reset_day:02d}", local.date().isoformat()


@dataclass
class Reservation:
    request_id: str
    elements: int
    billing_month: str
    billing_day: str


class UsageLedger:
    """SQLite-backed quota ledger. BEGIN IMMEDIATE serializes cap checks and reservations."""

    def __init__(self, path: Path, settings):
        self.path, self.settings = path, settings

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def reserve_google(self, origins: int, destinations: int, request_type="compute_route_matrix", run_id=None, now=None) -> Reservation:
        now = now or datetime.now(ZoneInfo(self.settings.google_billing_timezone))
        elements = matrix_elements(origins, destinations)
        if origins != 1:
            raise UsageLimitExceeded("normal Alpha Dispatch checks require exactly one matrix origin")
        if elements > self.settings.google_max_elements_per_refresh:
            raise UsageLimitExceeded(f"request needs {elements} elements; per-refresh cap is {self.settings.google_max_elements_per_refresh}")
        monthly_limit = effective_monthly_limit(self.settings)
        if self.settings.google_require_free_limit_configuration and monthly_limit is None:
            raise UsageLimitExceeded("monthly free allowance or explicit monthly element cap is not configured")
        month, day = billing_buckets(now, self.settings.google_billing_timezone, self.settings.google_billing_reset_day)
        ident = str(uuid.uuid4())
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            monthly = con.execute("SELECT COALESCE(SUM(element_count),0) FROM api_usage_ledger WHERE provider='google' AND service='routes' AND billing_month=? AND reserved=1", (month,)).fetchone()[0]
            daily = con.execute("SELECT COALESCE(SUM(element_count),0) FROM api_usage_ledger WHERE provider='google' AND service='routes' AND billing_day=? AND reserved=1", (day,)).fetchone()[0]
            # ALLOW_PAID_OVERAGE=false is the non-bypassable circuit breaker even
            # if other guard features are disabled.
            if not self.settings.google_allow_paid_overage:
                if monthly_limit is not None and monthly + elements > monthly_limit:
                    raise UsageLimitExceeded(f"monthly Google Routes safety limit: {monthly} of {monthly_limit} elements used")
                daily_limit = self.settings.google_max_daily_elements
                if daily_limit is not None and daily + elements > daily_limit:
                    raise UsageLimitExceeded(f"daily Google Routes safety limit: {daily} of {daily_limit} elements used")
            con.execute("""INSERT INTO api_usage_ledger(provider,service,sku_category,request_type,request_id,run_id,timestamp,billing_month,billing_day,origin_count,destination_count,element_count,cache_hit,status,reserved,completed)
                VALUES('google','routes',?,?,?,?,?,?,?,?,?,?,0,'reserved',1,0)""",
                ("route_matrix_traffic_aware" if "TRAFFIC" in self.settings.google_routing_preference else "route_matrix_basic", request_type, ident, run_id, now.isoformat(), month, day, origins, destinations, elements))
            con.commit()
            return Reservation(ident, elements, month, day)
        except Exception:
            con.rollback(); raise
        finally: con.close()

    def finish(self, reservation: Reservation, status="completed", error_type=None, release=False):
        with self._connect() as con:
            con.execute("UPDATE api_usage_ledger SET status=?, completed=?, reserved=?, error_type=? WHERE request_id=?", (status, int(status == "completed"), int(not release), error_type, reservation.request_id))

    def record_udot(self, request_id=None, now=None, status="completed", error_type=None):
        now = now or datetime.now(ZoneInfo(self.settings.google_billing_timezone)); month, day = billing_buckets(now, self.settings.google_billing_timezone, self.settings.google_billing_reset_day)
        with self._connect() as con:
            con.execute("""INSERT INTO api_usage_ledger(provider,service,request_type,request_id,timestamp,billing_month,billing_day,element_count,cache_hit,status,reserved,completed,error_type)
              VALUES('udot','traffic','rest_call',?,?,?,?,0,0,?,0,?,?)""", (request_id or str(uuid.uuid4()), now.isoformat(), month, day, status, int(status == "completed"), error_type))

    def usage(self, now=None):
        now = now or datetime.now(ZoneInfo(self.settings.google_billing_timezone)); month, day = billing_buckets(now, self.settings.google_billing_timezone, self.settings.google_billing_reset_day)
        with self._connect() as con:
            google_day = con.execute("SELECT COALESCE(SUM(element_count),0) FROM api_usage_ledger WHERE provider='google' AND service='routes' AND billing_day=? AND reserved=1", (day,)).fetchone()[0]
            google_month = con.execute("SELECT COALESCE(SUM(element_count),0) FROM api_usage_ledger WHERE provider='google' AND service='routes' AND billing_month=? AND reserved=1", (month,)).fetchone()[0]
            udot_day = con.execute("SELECT COUNT(*) FROM api_usage_ledger WHERE provider='udot' AND service='traffic' AND billing_day=? AND completed=1", (day,)).fetchone()[0]
        limit = effective_monthly_limit(self.settings)
        return {"google_today":google_day,"google_month":google_month,"google_daily_limit":self.settings.google_max_daily_elements,"google_monthly_limit":limit,"monthly_remaining":max(0, limit-google_month) if limit is not None else None,"udot_today":udot_day,"billing_month":month}
