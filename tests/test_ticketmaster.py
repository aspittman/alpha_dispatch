from datetime import datetime, timedelta, timezone

from driver_dispatch.sources.ticketmaster import TicketmasterSource


def test_ticketmaster_sends_utc_datetimes_without_microseconds(settings, tmp_path, monkeypatch):
    source = TicketmasterSource(tmp_path, settings.locations, api_key="test-key")
    captured = []
    monkeypatch.setattr(source, "get_json", lambda url, params: captured.append(params) or {})
    mountain_time = timezone(timedelta(hours=-6))

    source.collect(
        datetime(2026, 7, 17, 4, 42, 0, 648770, tzinfo=mountain_time),
        datetime(2026, 7, 24, 4, 42, 0, 648770, tzinfo=mountain_time),
    )

    assert captured[0]["startDateTime"] == "2026-07-17T10:42:00Z"
    assert captured[0]["endDateTime"] == "2026-07-24T10:42:00Z"
