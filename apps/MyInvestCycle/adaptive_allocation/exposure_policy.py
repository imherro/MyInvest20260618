from __future__ import annotations

from typing import Mapping

from adaptive_allocation.structural_bull_policy import refine_structural_bull_policy


RISK_BUDGET_ORDER = ("defensive", "low", "medium", "medium_high", "high")


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _adjust_budget(base: str, delta: int) -> str:
    index = RISK_BUDGET_ORDER.index(base)
    return RISK_BUDGET_ORDER[max(0, min(len(RISK_BUDGET_ORDER) - 1, index + delta))]


def _exposure_range(risk_budget: str) -> str:
    return {
        "defensive": "0-30%",
        "low": "30-50%",
        "medium": "50-70%",
        "medium_high": "60-80%",
        "high": "70-90%",
    }[risk_budget]


def determine_exposure_policy(
    structural_payload: Mapping[str, object],
    theme_risk_payload: Mapping[str, object],
) -> dict[str, object]:
    evidence = _section(structural_payload, "evidence")
    macro = _section(evidence, "macro")
    structure = _section(evidence, "market_structure")
    structural_state = str(structural_payload.get("structural_state", "RANGE"))
    theme_risk_level = str(theme_risk_payload.get("theme_risk_level", "medium"))
    refined_policy = refine_structural_bull_policy(structural_payload, theme_risk_payload)
    refined_applies = bool(refined_policy.get("applies"))

    if refined_applies:
        base = str(refined_policy.get("risk_budget") or "medium_high")
    elif structural_state == "BROAD_BULL":
        base = "high"
    elif structural_state == "STRUCTURAL_BULL_ROTATION":
        base = "medium_high"
    elif structural_state == "BEAR_REBOUND":
        base = "low"
    elif structural_state in {"BEAR_STRUCTURE", "WEAK_MARKET"}:
        base = "defensive"
    else:
        base = "medium"

    if not refined_applies:
        if str(macro.get("state")) == "BEAR":
            base = _adjust_budget(base, -2)
        elif str(macro.get("state")) == "BULL" and str(structure.get("state")) == "BULL_BROADENING":
            base = _adjust_budget(base, 1)

    if refined_applies:
        theme_delta = 0
    elif theme_risk_level == "high":
        base = _adjust_budget(base, -2)
        theme_delta = -2
    elif theme_risk_level == "medium":
        base = _adjust_budget(base, -1)
        theme_delta = -1
    elif theme_risk_level == "low":
        base = _adjust_budget(base, 0)
        theme_delta = 0
    else:
        theme_delta = 0

    return {
        "risk_budget": base,
        "equity_exposure_range": _exposure_range(base),
        "risk_adjustments": {
            "structural_state": structural_state,
            "allocation_structural_state": refined_policy.get("allocation_structural_state"),
            "macro_state": macro.get("state"),
            "market_structure_state": structure.get("state"),
            "theme_risk_level": theme_risk_level,
            "theme_risk_delta": theme_delta,
            "structural_bull_policy": refined_policy,
        },
    }
