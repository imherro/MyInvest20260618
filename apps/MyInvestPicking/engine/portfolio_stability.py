from __future__ import annotations

from math import log
from typing import Any


def compute_portfolio_stability(positions: list[dict[str, Any]]) -> dict[str, float]:
    if not positions:
        return {
            "turnover": 0.0,
            "exposure_drift": 0.0,
            "weight_entropy": 0.0,
            "stability_score": 0.0,
        }

    weights = [float(position.get("weight") or 0) for position in positions if position.get("weight")]
    entropy = _normalized_entropy(weights)
    max_weight = max(weights, default=0.0)
    stability_score = entropy * (1 - max_weight)
    return {
        "turnover": 0.0,
        "exposure_drift": 0.0,
        "weight_entropy": round(entropy, 4),
        "stability_score": round(stability_score, 4),
    }


def _normalized_entropy(weights: list[float]) -> float:
    total = sum(weights)
    if total <= 0 or len(weights) <= 1:
        return 0.0
    probabilities = [weight / total for weight in weights if weight > 0]
    entropy = -sum(probability * log(probability) for probability in probabilities)
    return entropy / log(len(probabilities))
