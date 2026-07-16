from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from driver_dispatch.config.settings import AppSettings, Location, Settings
from driver_dispatch.models import Event


@pytest.fixture
def settings(tmp_path):
    return Settings(app=AppSettings(database_path=str(tmp_path / "test.db"), cache_dir=str(tmp_path / "cache"), report_dir=str(tmp_path / "reports"), manual_events_file=str(tmp_path / "manual.yaml"), permitted_start_hour=5, permitted_end_hour=2), locations=[Location(name="Salt Lake City", latitude=40.7608, longitude=-111.8910)], venues={"Delta Center": {"capacity": 18000, "pickup_difficulty": .7}}, scoring={"category_weights": {"concert": 18, "other": 5}, "day_weights": {"Friday": 8}, "attendance_breakpoints": [[500, 3], [5000, 13], [15000, 20]], "confidence_fields": ["name", "venue_name", "city", "start_datetime", "estimated_attendance", "event_url"]})


@pytest.fixture
def event():
    return Event(source="manual", source_event_id="1", name="Example Concert", event_type="concert", venue_name="Delta Center", city="Salt Lake City", state="UT", latitude=40.7683, longitude=-111.9011, start_datetime=datetime(2026, 7, 17, 20, 0, tzinfo=ZoneInfo("America/Denver")), estimated_attendance=15000, attendance_confidence=.7, event_url="https://example.test/event")

