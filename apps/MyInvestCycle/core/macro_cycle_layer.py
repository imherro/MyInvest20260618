from __future__ import annotations

from typing import Mapping

from core.risk_score_engine import _clip, calculate_risk_score


MACRO_REGIME_LABELS = {
    "bull": "牛市主周期",
    "recovery": "修复周期",
    "contraction": "收缩周期",
    "bear": "熊市主周期",
}

EXPOSURE_CEILINGS = {
    "bull": 0.90,
    "recovery": 0.75,
    "contraction": 0.55,
    "bear": 0.35,
}


def _score(signal: Mapping[str, object], key: str, default: float = 0.5) -> float:
    return _clip(float(signal.get(key, default)))


def _feature(signal: Mapping[str, object], key: str, default: float = 0.0) -> float:
    features = signal.get("features")
    if isinstance(features, Mapping) and key in features:
        return float(features[key])
    return float(signal.get(key, default))


def _macro_score(signal: Mapping[str, object]) -> float:
    trend = _score(signal, "trend")
    breadth = _score(signal, "breadth")
    liquidity = _score(signal, "liquidity")
    regime_score = _score(signal, "regime_score")
    return _clip(0.42 * trend + 0.24 * regime_score + 0.18 * liquidity + 0.16 * breadth)


def _classify_macro_regime(signal: Mapping[str, object], macro_score: float, risk_score: float) -> str:
    trend = _score(signal, "trend")
    breadth = _score(signal, "breadth")
    regime_score = _score(signal, "regime_score")
    momentum_decay = _feature(signal, "momentum_decay", 0.0)

    if trend >= 0.55 and macro_score >= 0.55 and regime_score >= 0.48:
        return "bull"
    if trend <= 0.40 and macro_score <= 0.42 and risk_score >= 0.52:
        return "bear"
    if trend >= 0.45 and macro_score >= 0.45 and (momentum_decay >= -0.05 or breadth >= 0.48):
        return "recovery"
    return "contraction"


def _risk_overlay(signal: Mapping[str, object], risk_score: float) -> float:
    volatility = _score(signal, "volatility")
    breadth = _score(signal, "breadth")
    liquidity = _score(signal, "liquidity")
    structure_pressure = abs(_score(signal, "trend") - breadth)
    overlay = 0.45 * risk_score + 0.20 * (1.0 - volatility) + 0.20 * (1.0 - liquidity) + 0.15 * structure_pressure
    return _clip(overlay)


def build_macro_cycle_decision(signal: Mapping[str, object]) -> dict[str, object]:
    """Slow macro layer: only controls exposure, not style or ETF selection."""

    risk = calculate_risk_score(
        {
            "trend": _score(signal, "trend"),
            "breadth": _score(signal, "breadth"),
            "liquidity": _score(signal, "liquidity"),
            "volatility": _score(signal, "volatility"),
        }
    )
    risk_score = float(risk["risk_score"])
    macro_score = _macro_score(signal)
    macro_regime = _classify_macro_regime(signal, macro_score, risk_score)
    ceiling = EXPOSURE_CEILINGS[macro_regime]
    overlay = _risk_overlay(signal, risk_score)
    target_exposure = _clip(ceiling * (1.0 - 0.35 * overlay), 0.0, ceiling)

    return {
        "engine": "Macro Cycle Layer M2.1",
        "as_of": signal.get("as_of"),
        "macro_regime": macro_regime,
        "macro_label": MACRO_REGIME_LABELS[macro_regime],
        "macro_score": round(macro_score, 6),
        "exposure_ceiling": round(ceiling, 6),
        "risk_overlay": round(overlay, 6),
        "target_exposure": round(target_exposure, 6),
        "risk_score": round(risk_score, 6),
        "risk_components": risk["components"],
        "input": {
            "trend": _score(signal, "trend"),
            "breadth": _score(signal, "breadth"),
            "liquidity": _score(signal, "liquidity"),
            "volatility": _score(signal, "volatility"),
            "regime_score": _score(signal, "regime_score"),
            "momentum_decay": round(_feature(signal, "momentum_decay", 0.0), 6),
        },
        "constraints": {
            "macro_controls_exposure_only": True,
            "no_style_selection": True,
            "no_etf_selection": True,
            "no_trade_execution": True,
        },
    }
