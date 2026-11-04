from __future__ import annotations

from typing import Mapping

from core.risk_score_engine import _clip


STYLE_KEYS = ("growth", "value", "low_vol", "dividend", "small_cap", "cash_proxy")

REGIME_BASE_SCORES: dict[str, dict[str, float]] = {
    "bull": {
        "growth": 0.75,
        "value": 0.35,
        "low_vol": 0.25,
        "dividend": 0.25,
        "small_cap": 0.70,
        "cash_proxy": 0.10,
    },
    "range": {
        "growth": 0.45,
        "value": 0.65,
        "low_vol": 0.55,
        "dividend": 0.45,
        "small_cap": 0.40,
        "cash_proxy": 0.35,
    },
    "bear": {
        "growth": 0.20,
        "value": 0.50,
        "low_vol": 0.80,
        "dividend": 0.75,
        "small_cap": 0.15,
        "cash_proxy": 0.70,
    },
    "transition": {
        "growth": 0.25,
        "value": 0.45,
        "low_vol": 0.75,
        "dividend": 0.55,
        "small_cap": 0.20,
        "cash_proxy": 0.70,
    },
}


def _score(signal: Mapping[str, object], key: str, default: float = 0.5) -> float:
    return _clip(float(signal.get(key, default)))


def _risk_score(risk_decision: Mapping[str, object] | None) -> float:
    if not risk_decision:
        return 0.5
    return _clip(float(risk_decision.get("risk_score", 0.5)))


def _style_adjustments(
    regime_signal: Mapping[str, object],
    risk_decision: Mapping[str, object] | None,
) -> dict[str, float]:
    trend = _score(regime_signal, "trend")
    breadth = _score(regime_signal, "breadth")
    liquidity = _score(regime_signal, "liquidity")
    volatility_stability = _score(regime_signal, "volatility")
    risk = _risk_score(risk_decision)

    trend_tilt = trend - 0.5
    breadth_tilt = breadth - 0.5
    liquidity_tilt = liquidity - 0.5
    stability_tilt = volatility_stability - 0.5
    risk_tilt = risk - 0.5

    return {
        "growth": (
            0.20 * trend_tilt
            + 0.20 * breadth_tilt
            + 0.15 * liquidity_tilt
            + 0.10 * stability_tilt
            - 0.25 * risk_tilt
        ),
        "small_cap": (
            0.12 * trend_tilt
            + 0.22 * breadth_tilt
            + 0.20 * liquidity_tilt
            + 0.08 * stability_tilt
            - 0.22 * risk_tilt
        ),
        "value": (
            -0.05 * trend_tilt
            - 0.04 * liquidity_tilt
            + 0.08 * risk_tilt
            + 0.06 * (0.5 - breadth)
        ),
        "low_vol": (
            0.18 * risk_tilt
            + 0.20 * (0.5 - volatility_stability)
            + 0.12 * (0.5 - breadth)
        ),
        "dividend": (
            0.15 * risk_tilt
            + 0.10 * (0.5 - breadth)
            + 0.08 * (0.5 - liquidity)
        ),
        "cash_proxy": (
            0.25 * risk_tilt
            + 0.18 * (0.5 - volatility_stability)
            + 0.12 * (0.5 - trend)
        ),
    }


def _round_scores(scores: Mapping[str, float]) -> dict[str, float]:
    return {style: round(_clip(float(scores.get(style, 0.0))), 6) for style in STYLE_KEYS}


def _top_styles(style_scores: Mapping[str, float], limit: int = 3) -> list[dict[str, object]]:
    ranked = sorted(style_scores.items(), key=lambda item: item[1], reverse=True)
    return [{"style": style, "score": round(float(score), 6)} for style, score in ranked[:limit]]


def _reasoning(
    regime_signal: Mapping[str, object],
    risk_decision: Mapping[str, object] | None,
    style_scores: Mapping[str, float],
) -> list[str]:
    regime = str(regime_signal.get("regime", "unknown"))
    risk = _risk_score(risk_decision)
    breadth = _score(regime_signal, "breadth")
    liquidity = _score(regime_signal, "liquidity")
    volatility = _score(regime_signal, "volatility")
    top = ", ".join(item["style"] for item in _top_styles(style_scores))
    lines = [
        f"{regime} regime sets the base style preference.",
        f"Risk score {risk:.2f} shifts weight toward defensive styles when elevated.",
        f"Breadth {breadth:.2f}, liquidity {liquidity:.2f}, and volatility stability {volatility:.2f} adjust growth versus defensive preference.",
        f"Top styles are {top}.",
    ]
    return lines


def build_style_factor_snapshot(
    regime_signal: Mapping[str, object],
    risk_decision: Mapping[str, object] | None = None,
) -> dict[str, object]:
    regime = str(regime_signal.get("regime", "range"))
    if regime not in REGIME_BASE_SCORES:
        raise ValueError(f"Unknown regime for style factor engine: {regime!r}")

    base = REGIME_BASE_SCORES[regime]
    adjustments = _style_adjustments(regime_signal, risk_decision)
    raw_scores = {style: base[style] + adjustments[style] for style in STYLE_KEYS}
    style_scores = _round_scores(raw_scores)

    return {
        "engine": "Style Factor Engine A1.1",
        "as_of": regime_signal.get("as_of"),
        "regime": regime,
        "risk_score": round(_risk_score(risk_decision), 6),
        "input": {
            "trend": _score(regime_signal, "trend"),
            "breadth": _score(regime_signal, "breadth"),
            "liquidity": _score(regime_signal, "liquidity"),
            "volatility": _score(regime_signal, "volatility"),
            "regime_score": _score(regime_signal, "regime_score"),
            "confidence": _score(regime_signal, "confidence"),
        },
        "base_scores": _round_scores(base),
        "adjustments": {style: round(adjustments[style], 6) for style in STYLE_KEYS},
        "style_scores": style_scores,
        "top_styles": _top_styles(style_scores),
        "reasoning": _reasoning(regime_signal, risk_decision, style_scores),
        "constraints": {
            "asset_selection_layer": True,
            "etf_only": True,
            "no_single_stock_selection": True,
            "no_trade_execution": True,
            "no_prediction_of_market_direction": True,
        },
    }
