from __future__ import annotations

from collections import Counter
from statistics import pstdev
from typing import Iterable


def regime_flip_count(regimes: Iterable[str]) -> int:
    values = list(regimes)
    if len(values) < 2:
        return 0
    return sum(1 for left, right in zip(values, values[1:]) if left != right)


def dominant_regime(regimes: Iterable[str]) -> str | None:
    values = list(regimes)
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def regime_stability(regimes: Iterable[str]) -> float:
    values = list(regimes)
    if not values:
        return 0.0
    dominant = dominant_regime(values)
    stable_count = sum(1 for value in values if value == dominant)
    return round(stable_count / len(values), 4)


def score_drift(scores: Iterable[float]) -> float:
    values = [float(score) for score in scores]
    if not values:
        return 0.0
    return round(max(values) - min(values), 4)


def confidence_std(confidences: Iterable[float]) -> float:
    values = [float(confidence) for confidence in confidences]
    if len(values) < 2:
        return 0.0
    return round(pstdev(values), 4)


def guarded_confidence(confidence: float, regimes: Iterable[str], *, flip_threshold: int = 3) -> float:
    penalty = 0.8 if regime_flip_count(regimes) > flip_threshold else 1.0
    return round(max(0.0, min(1.0, confidence * penalty)), 4)


def drift_level(flip_count: int, trend_std: float, breadth_std: float) -> str:
    if flip_count >= 5 or trend_std >= 0.18 or breadth_std >= 0.22:
        return "high"
    if flip_count >= 2 or trend_std >= 0.10 or breadth_std >= 0.14:
        return "medium"
    return "low"
