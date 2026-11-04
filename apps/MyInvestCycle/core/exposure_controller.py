from __future__ import annotations

from typing import Mapping

from core.risk_score_engine import _clip, load_risk_policy, score_risk_signal


def _regime_policy(policy: Mapping[str, Mapping[str, object]], regime: str) -> Mapping[str, object]:
    if regime not in policy:
        raise KeyError(f"Missing risk policy for regime: {regime}")
    return policy[regime]


def _action_for_exposure(base_exposure: float, recommended_exposure: float) -> str:
    delta = recommended_exposure - base_exposure
    if delta <= -0.10:
        return "reduce"
    if delta >= 0.10:
        return "increase"
    return "hold"


def _alert_for(regime: str, risk_level: str) -> str:
    if risk_level == "high":
        return f"{regime} risk elevated"
    if regime == "transition":
        return "transition risk requires reduced trading"
    return "risk within policy band"


def build_exposure_decision(
    signal: Mapping[str, object],
    *,
    policy: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    resolved_policy = load_risk_policy() if policy is None else policy
    scored = score_risk_signal(signal, policy=resolved_policy)
    regime = str(signal["regime"])
    regime_policy = _regime_policy(resolved_policy, regime)

    base_exposure = float(regime_policy["base_exposure"])
    min_exposure = float(regime_policy.get("min_exposure", 0.0))
    max_exposure = float(regime_policy.get("max_exposure", 1.0))
    risk_score = float(scored["risk_score"])
    recommended_exposure = _clip(base_exposure * (1.0 - risk_score), min_exposure, max_exposure)
    risk_level = str(scored["risk_level"])

    return {
        "regime": regime,
        "risk_score": round(risk_score, 6),
        "risk_level": risk_level,
        "risk_components": scored["components"],
        "base_exposure": round(base_exposure, 6),
        "recommended_exposure": round(recommended_exposure, 6),
        "leverage_allowed": bool(regime_policy.get("leverage_allowed", False)) and risk_level == "low",
        "strategy_mode": str(regime_policy.get("strategy_mode", "hold")),
        "action": _action_for_exposure(base_exposure, recommended_exposure),
        "alert": _alert_for(regime, risk_level),
    }
