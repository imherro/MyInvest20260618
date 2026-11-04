from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from allocation_policy.opportunity_risk_state import normalize_opportunity_state, normalize_risk_state


POLICY_MODES = (
    "rebuild_risk",
    "participate",
    "participate_selectively",
    "participate_with_control",
    "late_cycle_control",
    "protect_capital",
    "defensive",
    "watch_only",
)


@dataclass(frozen=True)
class OpportunityRiskPolicy:
    opportunity_state: str
    risk_state: str
    policy_mode: str
    actions_allowed: tuple[str, ...]
    actions_blocked: tuple[str, ...]
    evidence: tuple[str, ...]
    interpretation: str


def map_opportunity_risk_policy(
    opportunity_state: object,
    risk_state: object,
    evidence: tuple[str, ...] | list[str] | None = None,
) -> OpportunityRiskPolicy:
    opportunity = normalize_opportunity_state(opportunity_state)
    risk = normalize_risk_state(risk_state)
    evidence_tuple = tuple(str(item) for item in (evidence or []))

    policy_mode = "watch_only"
    actions_allowed = ("observe_environment",)
    actions_blocked = ("aggressive_expansion", "automatic_allocation")

    if opportunity == "EARLY_RECOVERY":
        if risk in {"LOW_RISK", "NORMAL"}:
            policy_mode = "rebuild_risk"
            actions_allowed = ("rebuild_risk_attention", "require_breadth_confirmation")
            actions_blocked = ("aggressive_expansion", "full_beta_assumption")
        else:
            policy_mode = "participate_with_control"
            actions_allowed = ("maintain_recovery_attention", "require_crowding_control")
            actions_blocked = ("aggressive_expansion", "theme_chasing")
    elif opportunity == "BULL_EXPANSION":
        if risk == "LOW_RISK":
            policy_mode = "participate"
            actions_allowed = ("allow_participation_study", "monitor_breadth")
            actions_blocked = ("ignore_crowding", "single_theme_concentration")
        elif risk == "NORMAL":
            policy_mode = "participate_selectively"
            actions_allowed = ("allow_selective_participation_study", "monitor_rotation_health")
            actions_blocked = ("unrestricted_expansion",)
        else:
            policy_mode = "participate_with_control"
            actions_allowed = ("maintain_opportunity_attention", "require_crowding_control")
            actions_blocked = ("aggressive_expansion", "single_theme_concentration")
    elif opportunity == "STRUCTURAL_ROTATION":
        if risk in {"LOW_RISK", "NORMAL"}:
            policy_mode = "participate_selectively"
            actions_allowed = ("allow_structural_rotation_study", "require_theme_persistence")
            actions_blocked = ("broad_beta_assumption",)
        else:
            policy_mode = "participate_with_control"
            actions_allowed = ("maintain_opportunity_attention", "require_crowding_control", "require_breadth_confirmation")
            actions_blocked = ("aggressive_expansion", "theme_chasing", "single_theme_concentration")
    elif opportunity == "LATE_BULL":
        if risk == "HIGH_RISK":
            policy_mode = "protect_capital"
            actions_allowed = ("protect_existing_gains", "raise_review_threshold")
            actions_blocked = ("aggressive_expansion", "new_high_beta_budget", "theme_chasing")
        else:
            policy_mode = "late_cycle_control"
            actions_allowed = ("maintain_opportunity_attention", "protect_existing_gains", "require_crowding_control")
            actions_blocked = ("aggressive_expansion", "new_unconfirmed_beta")
    elif opportunity == "DEFENSIVE_REPAIR":
        policy_mode = "defensive"
        actions_allowed = ("prioritize_risk_repair", "wait_for_recovery_confirmation")
        actions_blocked = ("offensive_expansion", "theme_chasing")

    return OpportunityRiskPolicy(
        opportunity_state=opportunity,
        risk_state=risk,
        policy_mode=policy_mode,
        actions_allowed=actions_allowed,
        actions_blocked=actions_blocked,
        evidence=evidence_tuple,
        interpretation=_interpret_policy(policy_mode),
    )


def policy_to_payload(policy: OpportunityRiskPolicy) -> dict[str, object]:
    return {
        "opportunity_state": policy.opportunity_state,
        "risk_state": policy.risk_state,
        "policy_mode": policy.policy_mode,
        "actions_allowed": list(policy.actions_allowed),
        "actions_blocked": list(policy.actions_blocked),
        "evidence": list(policy.evidence),
        "interpretation": policy.interpretation,
        "constraints": {
            "policy_mapping_only": True,
            "no_allocation": True,
            "no_weight": True,
            "no_trade": True,
        },
    }


def map_row_policy(row: Mapping[str, object]) -> dict[str, object]:
    policy = map_opportunity_risk_policy(
        row.get("opportunity_state"),
        row.get("risk_state"),
        tuple(str(item) for item in (row.get("evidence") or [])),
    )
    return policy_to_payload(policy)


def _interpret_policy(policy_mode: str) -> str:
    interpretations = {
        "rebuild_risk": "Recovery exists but needs confirmation before higher beta research.",
        "participate": "Opportunity and low risk allow participation research, without producing weights.",
        "participate_selectively": "Opportunity exists but should remain selective and evidence-gated.",
        "participate_with_control": "Opportunity exists, but crowding or narrow breadth requires control before expansion.",
        "late_cycle_control": "Late-cycle opportunity remains visible, but policy should protect gains and block aggressive expansion.",
        "protect_capital": "Late-cycle/high-risk state prioritizes capital protection over new risk expansion.",
        "defensive": "Weak opportunity or high risk favors defensive repair and recovery confirmation.",
        "watch_only": "State is inconclusive; observe only and do not map to allocation.",
    }
    return interpretations.get(policy_mode, "Policy mode is unknown; observe only.")
