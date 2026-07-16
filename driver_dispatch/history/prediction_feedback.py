SCORING_VERSION = "v1-rules"


def prediction_error(predicted_score: float, actual_net_per_hour: float, target_net_per_hour: float = 25) -> float:
    actual_index = min(100, max(0, actual_net_per_hour / target_net_per_hour * 60))
    return round(actual_index - predicted_score, 2)

