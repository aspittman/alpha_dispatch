from driver_dispatch.scoring.opportunity_score import score_event


def test_scores_are_separate_and_explainable(event, settings):
    result = score_event(event, settings)
    assert 0 <= result.opportunity_score <= 100
    assert 0 <= result.confidence_score <= 100
    assert result.reasons and result.opportunity_score != result.confidence_score


def test_weather_adjustment_and_safety(event, settings):
    clear = score_event(event.model_copy(update={"weather": {"risk": 5, "short_forecast": "Clear"}}), settings)
    storm = score_event(event.model_copy(update={"weather": {"risk": 95, "short_forecast": "Blizzard"}}), settings)
    assert storm.opportunity_score < clear.opportunity_score
    assert storm.suppressed


def test_canceled_event_suppressed(event, settings):
    result = score_event(event.model_copy(update={"status": "canceled"}), settings)
    assert result.suppressed
    assert any("canceled" in reason for reason in result.suppression_reasons)

