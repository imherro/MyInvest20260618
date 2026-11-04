from __future__ import annotations

from typing import Mapping

from core.risk_score_engine import _clip


STYLE_KEYS = ("growth", "value", "low_vol", "dividend", "small_cap")

BASE_STYLE_WEIGHTS: dict[str, dict[str, float]] = {
    "bull": {
        "growth": 0.30,
        "value": 0.20,
        "low_vol": 0.10,
        "dividend": 0.15,
        "small_cap": 0.25,
    },
    "recovery": {
        "growth": 0.25,
        "value": 0.25,
        "low_vol": 0.15,
        "dividend": 0.15,
        "small_cap": 0.20,
    },
    "contraction": {
        "growth": 0.10,
        "value": 0.25,
        "low_vol": 0.30,
        "dividend": 0.30,
        "small_cap": 0.05,
    },
    "bear": {
        "growth": 0.05,
        "value": 0.20,
        "low_vol": 0.35,
        "dividend": 0.35,
        "small_cap": 0.05,
    },
}


def _score(signal: Mapping[str, object], key: str, default: float = 0.5) -> float:
    return _clip(float(signal.get(key, default)))


def _normalize(weights: Mapping[str, float]) -> dict[str, float]:
    positive = {style: max(0.0, float(weights.get(style, 0.0))) for style in STYLE_KEYS}
    total = sum(positive.values())
    if total <= 0:
        return {style: round(1.0 / len(STYLE_KEYS), 6) for style in STYLE_KEYS}
    normalized = {style: positive[style] / total for style in STYLE_KEYS}
    rounded = {style: round(value, 6) for style, value in normalized.items()}
    drift = round(1.0 - sum(rounded.values()), 6)
    if drift:
        largest = max(rounded, key=rounded.get)
        rounded[largest] = round(rounded[largest] + drift, 6)
    return rounded


def _style_adjustments(signal: Mapping[str, object], macro_decision: Mapping[str, object]) -> dict[str, float]:
    trend = _score(signal, "trend")
    breadth = _score(signal, "breadth")
    liquidity = _score(signal, "liquidity")
    volatility = _score(signal, "volatility")
    risk_overlay = _clip(float(macro_decision.get("risk_overlay", 0.0)))

    trend_tilt = trend - 0.5
    breadth_tilt = breadth - 0.5
    liquidity_tilt = liquidity - 0.5
    stability_tilt = volatility - 0.5
    defensive_tilt = risk_overlay - 0.35

    return {
        "growth": 0.18 * trend_tilt + 0.12 * liquidity_tilt + 0.08 * stability_tilt - 0.16 * defensive_tilt,
        "small_cap": 0.20 * breadth_tilt + 0.15 * liquidity_tilt + 0.05 * trend_tilt - 0.16 * defensive_tilt,
        "value": 0.08 * trend_tilt + 0.08 * (0.5 - breadth) + 0.04 * defensive_tilt,
        "low_vol": 0.20 * defensive_tilt + 0.14 * (0.5 - volatility) + 0.08 * (0.5 - breadth),
        "dividend": 0.18 * defensive_tilt + 0.12 * (0.5 - breadth) + 0.08 * (0.5 - liquidity),
    }


def build_style_allocation(
    signal: Mapping[str, object],
    macro_decision: Mapping[str, object],
) -> dict[str, object]:
    """Mid-frequency style layer: controls style split only."""

    macro_regime = str(macro_decision.get("macro_regime", "recovery"))
    base = BASE_STYLE_WEIGHTS.get(macro_regime, BASE_STYLE_WEIGHTS["recovery"])
    adjustments = _style_adjustments(signal, macro_decision)
    raw = {style: base[style] + adjustments[style] for style in STYLE_KEYS}
    allocation = _normalize(raw)
    ranked = sorted(allocation.items(), key=lambda item: item[1], reverse=True)

    return {
        "engine": "Style Allocation Engine M2.1",
        "as_of": signal.get("as_of"),
        "macro_regime": macro_regime,
        "style_allocation": allocation,
        "top_styles": [{"style": style, "weight": weight} for style, weight in ranked[:3]],
        "base_weights": {style: round(base[style], 6) for style in STYLE_KEYS},
        "adjustments": {style: round(adjustments[style], 6) for style in STYLE_KEYS},
        "input": {
            "trend": _score(signal, "trend"),
            "breadth": _score(signal, "breadth"),
            "liquidity": _score(signal, "liquidity"),
            "volatility": _score(signal, "volatility"),
            "risk_overlay": round(float(macro_decision.get("risk_overlay", 0.0)), 6),
        },
        "constraints": {
            "style_controls_weights_only": True,
            "no_exposure_override": True,
            "no_etf_selection": True,
            "no_trade_execution": True,
        },
    }
