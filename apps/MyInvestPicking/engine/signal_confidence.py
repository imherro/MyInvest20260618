from __future__ import annotations

from typing import Any


def calculate_signal_confidence(
    position: dict[str, Any],
    market_regime: dict[str, Any],
    tradability: dict[str, Any],
) -> dict[str, Any]:
    factors = position.get("factors") or {}
    metrics = position.get("metrics") or {}
    components = {
        "factor_consistency": _factor_consistency(factors),
        "regime_alignment": _regime_alignment(factors, market_regime),
        "volume_confirmation": _volume_confirmation(metrics),
        "timeframe_alignment": _timeframe_alignment(metrics),
        "factor_health": _factor_health(position),
    }
    confidence = (
        0.25 * components["factor_consistency"]
        + 0.25 * components["regime_alignment"]
        + 0.20 * components["volume_confirmation"]
        + 0.15 * components["timeframe_alignment"]
        + 0.15 * components["factor_health"]
    )
    if not tradability.get("tradable"):
        confidence = min(confidence, 0.35)

    return {
        "confidence": round(_clip(confidence), 4),
        "components": {key: round(_clip(value), 4) for key, value in components.items()},
    }


def _factor_consistency(factors: dict[str, Any]) -> float:
    values = [
        _value(factors.get("trend", factors.get("momentum"))),
        _value(factors.get("growth")),
        _value(factors.get("quality")),
        _value(factors.get("industry_strength")),
    ]
    average = sum(values) / len(values)
    dispersion = max(values) - min(values)
    return average * (1 - min(dispersion, 0.60) * 0.35)


def _regime_alignment(factors: dict[str, Any], market_regime: dict[str, Any]) -> float:
    state = str(market_regime.get("state") or "range")
    momentum = _value(factors.get("momentum"))
    trend = _value(factors.get("trend"), momentum)
    growth = _value(factors.get("growth"))
    industry_strength = _value(factors.get("industry_strength"))
    quality = _value(factors.get("quality"))
    value = _value(factors.get("value"))
    risk = _value(factors.get("risk"))
    if state in {"ignored", "full_shadow"}:
        return 0.35 * trend + 0.25 * growth + 0.20 * industry_strength + 0.15 * quality + 0.05 * risk
    if state == "trend":
        return 0.50 * trend + 0.25 * growth + 0.15 * industry_strength + 0.10 * quality
    if state == "crash":
        return 0.65 * risk + 0.25 * quality + 0.10 * value
    if state == "high_vol":
        return 0.55 * risk + 0.25 * quality + 0.20 * value
    return 0.30 * trend + 0.25 * growth + 0.20 * industry_strength + 0.15 * quality + 0.10 * risk


def _volume_confirmation(metrics: dict[str, Any]) -> float:
    volume_ratio = _optional_float(metrics.get("volume_ratio"))
    turnover_rate = _optional_float(metrics.get("turnover_rate"))
    score = 0.50
    if volume_ratio is not None:
        if 0.80 <= volume_ratio <= 3.50:
            score += min(volume_ratio / 5.0, 0.35)
        elif volume_ratio > 3.50:
            score += 0.15
        else:
            score -= 0.15
    if turnover_rate is not None:
        if turnover_rate >= 1.0:
            score += 0.15
        elif turnover_rate < 0.5:
            score -= 0.20
    return score


def _timeframe_alignment(metrics: dict[str, Any]) -> float:
    momentum_5d = _optional_float(metrics.get("momentum_5d"))
    momentum_20d = _optional_float(metrics.get("momentum_20d"))
    momentum_60d = _optional_float(metrics.get("momentum_60d"))
    momentum_120d = _optional_float(metrics.get("momentum_120d"))
    if momentum_5d is None or momentum_20d is None:
        return 0.50
    medium_terms = [
        value for value in [momentum_60d, momentum_120d] if value is not None
    ]
    medium_positive = sum(value > 0 for value in medium_terms)
    if momentum_5d > 0 and momentum_20d > 0 and medium_positive == len(medium_terms):
        return 0.90 if momentum_5d <= max(momentum_20d, 0.001) * 2.5 else 0.75
    if momentum_20d > 0 and medium_positive > 0:
        return 0.75
    if momentum_5d >= 0 and momentum_20d >= -0.02:
        return 0.65
    if momentum_5d < 0 and momentum_20d < 0:
        return 0.20
    return 0.40


def _factor_health(position: dict[str, Any]) -> float:
    return _value(position.get("factor_health_score"))


def _value(value: Any, default: float = 0.50) -> float:
    parsed = _optional_float(value)
    return _clip(default if parsed is None else parsed)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clip(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
