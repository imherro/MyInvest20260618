from __future__ import annotations

from typing import Mapping


ScoreMap = Mapping[str, float]


def _score(scores: ScoreMap, key: str) -> float:
    value = float(scores.get(key, 0.0))
    return max(0.0, min(1.0, value))


def factor_drivers(scores: ScoreMap) -> dict[str, list[str]]:
    trend = _score(scores, "trend")
    breadth = _score(scores, "breadth")
    liquidity = _score(scores, "liquidity")
    volatility = _score(scores, "volatility")

    bullish: list[str] = []
    bearish: list[str] = []
    stabilizing: list[str] = []
    mixed: list[str] = []

    if trend >= 0.65:
        bullish.append("trend_strength")
    elif trend < 0.40:
        bearish.append("low_trend_signal")
    else:
        mixed.append("neutral_trend")

    if breadth >= 0.60:
        bullish.append("breadth_expansion")
    elif breadth < 0.40:
        bearish.append("weak_breadth")
    else:
        mixed.append("mixed_breadth")

    if liquidity >= 0.60:
        bullish.append("liquidity_strength")
    elif liquidity < 0.40:
        bearish.append("liquidity_weakness")
    else:
        mixed.append("neutral_liquidity")

    if volatility >= 0.65:
        stabilizing.append("volatility_stability")
    elif volatility < 0.40:
        bearish.append("volatility_stress")
    else:
        mixed.append("neutral_volatility")

    return {
        "bullish": bullish,
        "bearish": bearish,
        "stabilizing": stabilizing,
        "mixed": mixed,
    }


def explain_regime(regime_payload: Mapping[str, object]) -> dict[str, object]:
    regime = str(regime_payload["regime"])
    scores = regime_payload.get("sub_scores")
    if not isinstance(scores, Mapping):
        scores = {
            "trend": regime_payload.get("trend_score", 0.0),
            "breadth": regime_payload.get("breadth_score", 0.0),
            "liquidity": regime_payload.get("liquidity_score", 0.0),
            "volatility": regime_payload.get("volatility_score", 0.0),
        }

    drivers = factor_drivers(scores)
    bullish = drivers["bullish"]
    bearish = drivers["bearish"]
    stabilizing = drivers["stabilizing"]
    mixed = drivers["mixed"]

    if regime == "bull":
        primary = bullish + stabilizing
        negative = bearish
    elif regime == "bear":
        primary = bearish
        negative = bullish + stabilizing
    elif regime == "transition":
        primary = bullish + bearish
        negative = mixed
    else:
        primary = mixed + stabilizing
        negative = bullish + bearish

    primary = primary or ["mixed_signals"]
    explanation = build_explanation(regime, primary, negative)

    return {
        "regime": regime,
        "drivers": primary + negative,
        "primary_drivers": primary,
        "negative_drivers": negative,
        "explanation": explanation,
        "sub_scores": {
            "trend": round(_score(scores, "trend"), 4),
            "breadth": round(_score(scores, "breadth"), 4),
            "liquidity": round(_score(scores, "liquidity"), 4),
            "volatility": round(_score(scores, "volatility"), 4),
        },
    }


def build_explanation(regime: str, primary: list[str], negative: list[str]) -> str:
    primary_text = ", ".join(primary)
    if negative:
        negative_text = ", ".join(negative)
        verb = "constrains" if len(negative) == 1 else "constrain"
        return f"Regime is {regime} because the dominant drivers are {primary_text}, while {negative_text} {verb} the signal."
    return f"Regime is {regime} because the dominant drivers are {primary_text}."
