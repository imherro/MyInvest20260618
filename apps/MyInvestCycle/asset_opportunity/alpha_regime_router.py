from __future__ import annotations

from pathlib import Path
from typing import Mapping

from asset_opportunity.regime_alpha_schema import AlphaRegimeDecision
from asset_opportunity.regime_conditioned_validation import DEFAULT_STATE_PATH, _read_state_signals, _state_for_date
from core.data_loader import normalize_trade_date


def _is_high_crowding(state: Mapping[str, object]) -> bool:
    return (
        str(state.get("theme_risk_level") or "").lower() == "high"
        or str(state.get("allocation_structural_state") or "") == "STRUCTURAL_BULL_OVERHEATED"
    )


def _route(state: Mapping[str, object]) -> tuple[str, str, tuple[str, ...]]:
    structural_state = str(state.get("structural_state") or "UNKNOWN")
    macro_state = str(state.get("macro_state") or "UNKNOWN")
    market_structure = str(state.get("market_structure_state") or "UNKNOWN")
    theme_risk = str(state.get("theme_risk_level") or "unknown")
    if _is_high_crowding(state):
        return (
            "HIGH_CROWDING",
            "defensive_quality",
            (
                f"theme_risk_level={theme_risk} or structural bull policy is overheated",
                "high crowding regimes should avoid chasing extended themes",
            ),
        )
    if structural_state == "STRUCTURAL_BULL_ROTATION":
        return (
            "STRUCTURAL_BULL",
            "rotation_alpha",
            (
                "structural_state=STRUCTURAL_BULL_ROTATION",
                f"market_structure_state={market_structure}",
                "use rotation model placeholder; do not reuse broad trend score blindly",
            ),
        )
    if structural_state == "BROAD_BULL":
        return (
            "BROAD_BULL",
            "trend_following",
            (
                "structural_state=BROAD_BULL",
                f"macro_state={macro_state}",
                "broad bull validation showed trend/strength can be conditionally useful",
            ),
        )
    if structural_state == "RANGE":
        return (
            "RANGE",
            "mean_reversion",
            (
                "structural_state=RANGE",
                "range regimes require mean-reversion research before allocation",
            ),
        )
    if structural_state.startswith("BEAR"):
        return (
            "BEAR",
            "defensive_quality",
            (
                f"structural_state={structural_state}",
                "bear regimes prioritize defense and quality filters",
            ),
        )
    return (
        "RANGE",
        "mean_reversion",
        (
            f"structural_state={structural_state} is not mapped explicitly",
            "fallback to range/mean-reversion research mode",
        ),
    )


def build_alpha_regime_decision(
    date: str | int,
    *,
    state_path: str | Path = DEFAULT_STATE_PATH,
) -> dict[str, object]:
    requested_date = normalize_trade_date(date)
    state = _state_for_date(requested_date, _read_state_signals(state_path))
    alpha_regime, model, reason = _route(state)
    decision = AlphaRegimeDecision(
        date=requested_date,
        state_signal_date=None if state.get("state_signal_date") is None else str(state.get("state_signal_date")),
        alpha_regime=alpha_regime,
        recommended_model=model,
        structural_state=str(state.get("structural_state") or "UNKNOWN"),
        macro_state=str(state.get("macro_state") or "UNKNOWN"),
        market_structure_state=str(state.get("market_structure_state") or "UNKNOWN"),
        theme_risk_level=str(state.get("theme_risk_level") or "unknown"),
        reason=reason,
    )
    return {
        "engine": "V3.3.1 Alpha Regime Router Foundation",
        **decision.to_dict(),
        "constraints": {
            "state_signal_uses_last_known_signal": True,
            "no_new_factor": True,
            "does_not_change_opportunity_score": True,
            "no_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_backtest": True,
        },
    }
