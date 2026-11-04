from __future__ import annotations

from typing import Mapping


DECISION_MODES = (
    "FULL_PARTICIPATION",
    "SELECTIVE_PARTICIPATION",
    "PROTECTED_PARTICIPATION",
    "DEFENSIVE",
    "WAIT",
)

CAUTION_MODES = ("PROTECTED_PARTICIPATION", "DEFENSIVE", "WAIT")
PARTICIPATION_MODES = ("FULL_PARTICIPATION", "SELECTIVE_PARTICIPATION")


def context_value(row: Mapping[str, object], field: str) -> str:
    context = row.get("analysis_context")
    if not isinstance(context, Mapping):
        return "UNKNOWN"
    return str(context.get(field) or "UNKNOWN")


def decision_context(row: Mapping[str, object]) -> dict[str, object]:
    risk_bucket = str(row.get("risk_gradient_bucket") or "unknown")
    high_risk = risk_bucket == "high_risk"
    opportunity_state = context_value(row, "opportunity_state")
    market_phase = context_value(row, "market_phase")
    risk_state = context_value(row, "risk_state")

    if high_risk and market_phase == "CONTRACTION":
        mode = "DEFENSIVE"
        reason = "high_risk_gradient_in_contraction"
    elif high_risk and risk_state == "CROWDED":
        mode = "PROTECTED_PARTICIPATION"
        reason = "high_risk_gradient_with_crowding"
    elif market_phase == "CONTRACTION":
        mode = "WAIT"
        reason = "contraction_without_high_risk_gradient"
    elif opportunity_state == "BULL_EXPANSION" and not high_risk:
        mode = "FULL_PARTICIPATION"
        reason = "bull_expansion_without_high_risk_gradient"
    elif opportunity_state == "STRUCTURAL_ROTATION" or market_phase == "ROTATION":
        mode = "SELECTIVE_PARTICIPATION"
        reason = "structural_or_rotation_context"
    elif opportunity_state == "EARLY_RECOVERY" and market_phase == "EARLY_CYCLE":
        mode = "SELECTIVE_PARTICIPATION"
        reason = "early_recovery_early_cycle_context"
    else:
        mode = "WAIT"
        reason = "unclear_context_wait_for_confirmation"

    return {
        "decision_mode": mode,
        "reason": reason,
        "opportunity_state": opportunity_state,
        "market_phase": market_phase,
        "risk_state": risk_state,
        "risk_gradient_bucket": risk_bucket,
        "risk_gradient_score": row.get("risk_gradient_score"),
        "research_label_only": True,
    }
