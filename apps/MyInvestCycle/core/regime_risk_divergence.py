from __future__ import annotations

from typing import Mapping


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def calculate_regime_risk_divergence(
    regime_signal: Mapping[str, object],
    risk_decision: Mapping[str, object],
) -> dict[str, object]:
    regime = str(regime_signal.get("regime", "unknown"))
    regime_score = _clip(float(regime_signal.get("regime_score", 0.0)))
    risk_score = _clip(float(risk_decision.get("risk_score", 0.0)))
    score_gap = abs(regime_score - risk_score)

    bullish_risk_conflict = 0.0
    if regime == "bull":
        bullish_risk_conflict = regime_score * risk_score
    elif regime == "range":
        bullish_risk_conflict = 0.5 * regime_score * risk_score

    strength = _clip(max(score_gap, bullish_risk_conflict))
    return {
        "name": "regime_risk_divergence",
        "strength": round(strength, 6),
        "regime": regime,
        "regime_score": round(regime_score, 6),
        "risk_score": round(risk_score, 6),
        "score_gap": round(score_gap, 6),
        "bullish_risk_conflict": round(bullish_risk_conflict, 6),
        "interpretation": _interpret_regime_risk(regime, strength),
    }


def _interpret_regime_risk(regime: str, strength: float) -> str:
    if strength >= 0.6:
        return f"{regime} regime conflicts strongly with risk pressure"
    if strength >= 0.25:
        return f"{regime} regime shows measurable risk divergence"
    return f"{regime} regime and risk layer are broadly aligned"
