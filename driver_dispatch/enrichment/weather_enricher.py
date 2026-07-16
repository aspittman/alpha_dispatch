from driver_dispatch.models import Event


def enrich_weather(event: Event, source) -> Event:
    if event.latitude is not None and event.longitude is not None and event.start_datetime:
        event.weather = source.forecast(event.latitude, event.longitude, event.start_datetime)
    return event

