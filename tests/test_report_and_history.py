from datetime import date, datetime, timedelta

from driver_dispatch.models import DrivingSession
from driver_dispatch.planning.weekly_schedule import build_schedule
from driver_dispatch.reports.weekly_report import render_reports
from driver_dispatch.scoring.opportunity_score import score_event


def test_report_generation(event, settings, tmp_path):
    opportunity = score_event(event, settings)
    schedule = build_schedule([opportunity], 20)
    html, text = render_reports(date(2026, 7, 16), [opportunity], schedule, [], tmp_path)
    assert "Driver Dispatch Intelligence" in html.read_text()
    assert "Opportunity" in text.read_text()
    assert "Drive for arrival:" in text.read_text()
    assert "Where: Delta Center, Salt Lake City, UT" in text.read_text()
    assert "RECOMMENDED WEEKLY DRIVE PLAN" in text.read_text()
    assert "not affiliated" in text.read_text()


def test_session_metrics():
    start = datetime(2026, 7, 1, 18); session = DrivingSession(date=start.date(), start_datetime=start, end_datetime=start + timedelta(hours=4), gross_earnings=120, miles_driven=80, estimated_fuel_cost=20, trips_completed=8)
    assert session.metrics()["gross_per_hour"] == 30
    assert session.metrics()["net_per_mile"] == 1.25
