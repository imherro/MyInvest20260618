from __future__ import annotations

from typing import Mapping

from adaptive_exposure.exposure_schema import ExposureDecision, normalize_exposure_level


def map_policy_to_exposure(
    policy_row: Mapping[str, object],
    phase_row: Mapping[str, object] | None = None,
) -> ExposureDecision:
    policy_mode = str(policy_row.get("policy_mode") or "watch_only")
    risk_state = str(policy_row.get("risk_state") or "UNKNOWN")
    opportunity_state = str(policy_row.get("opportunity_state") or "UNKNOWN")
    phase = str((phase_row or {}).get("phase") or "UNKNOWN")
    reasons = list(policy_row.get("evidence") or policy_row.get("source_evidence") or [])
    blocked = list(policy_row.get("actions_blocked") or [])

    level = "BALANCED"
    band = "balanced_research_exposure"
    if policy_mode in {"protect_capital", "defensive"}:
        level = "DEFENSIVE"
        band = "defensive_research_exposure"
    elif policy_mode in {"late_cycle_control", "watch_only"}:
        level = "LOW"
        band = "low_research_exposure"
    elif policy_mode in {"rebuild_risk", "participate_with_control"}:
        level = "BALANCED"
        band = "balanced_with_controls"
    elif policy_mode == "participate_selectively":
        level = "BALANCED"
        band = "selective_balanced_research_exposure"
    elif policy_mode == "participate":
        level = "HIGH"
        band = "high_research_exposure"

    if risk_state == "HIGH_RISK" and level in {"BALANCED", "HIGH", "OFFENSIVE"}:
        level = "LOW"
        band = "risk_reduced_research_exposure"
        reasons.append("high_risk_state_caps_exposure_level")
    elif risk_state == "CROWDED" and phase == "LATE_CYCLE" and level == "HIGH":
        level = "BALANCED"
        band = "late_cycle_crowding_control"
        reasons.append("late_cycle_crowding_blocks_high_exposure")

    if opportunity_state == "BULL_EXPANSION" and risk_state == "LOW_RISK" and phase == "EXPANSION":
        level = "HIGH"
        band = "high_research_exposure"
        reasons.append("opportunity_and_phase_aligned")

    level = normalize_exposure_level(level)
    return ExposureDecision(
        policy_mode=policy_mode,
        exposure_level=level,
        exposure_band=band,
        reasons=tuple(dict.fromkeys(str(item) for item in reasons)),
        blocked=tuple(dict.fromkeys(str(item) for item in blocked)),
        explanation=_explain(level, policy_mode, phase, risk_state),
    )


def decision_to_payload(decision: ExposureDecision) -> dict[str, object]:
    return {
        "policy_mode": decision.policy_mode,
        "exposure_level": decision.exposure_level,
        "exposure_band": decision.exposure_band,
        "reasons": list(decision.reasons),
        "blocked": list(decision.blocked),
        "explanation": decision.explanation,
        "constraints": {
            "simulation_only": True,
            "qualitative_level_only": True,
            "no_percentage": True,
            "no_weight": True,
            "no_trade": True,
        },
    }


def _explain(level: str, policy_mode: str, phase: str, risk_state: str) -> str:
    return (
        f"Policy mode {policy_mode} maps to qualitative exposure level {level} "
        f"under phase {phase} and risk state {risk_state}; this is simulation-only."
    )
