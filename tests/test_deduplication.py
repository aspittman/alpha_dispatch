from driver_dispatch.normalization.deduplicator import deduplicate


def test_duplicate_sources_merge(event):
    other = event.model_copy(update={"source": "ticketmaster", "source_event_id": "tm1", "estimated_attendance": None, "event_url": None})
    unique, uncertain = deduplicate([event, other])
    assert len(unique) == 1 and not uncertain
    assert set(unique[0].source_attributions) == {"manual", "ticketmaster"}


def test_low_confidence_not_silently_merged(event):
    other = event.model_copy(update={"name": "Different Expo", "venue_name": "Salt Palace"})
    unique, _ = deduplicate([event, other])
    assert len(unique) == 2

