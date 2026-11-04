from __future__ import annotations

from typing import Mapping


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _num(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def refine_structural_bull_policy(
    structural_payload: Mapping[str, object],
    theme_risk_payload: Mapping[str, object],
) -> dict[str, object]:
    """Derive an allocation-only structural bull subtype without changing source signals."""

    structural_state = str(structural_payload.get("structural_state") or "RANGE")
    evidence = _section(structural_payload, "evidence")
    industry = _section(evidence, "industry_opportunity")
    market_structure = _section(evidence, "market_structure")
    metrics = _section(industry, "metrics")
    theme_risk_level = str(theme_risk_payload.get("theme_risk_level") or "medium")
    crowding_score = _num(theme_risk_payload.get("crowding_score"))
    quality_score = _num(theme_risk_payload.get("quality_score"))
    industry_strength = _num(industry.get("industry_strength"))
    theme_persistence = _num(industry.get("theme_persistence"))
    rotation_health = _num(industry.get("rotation_health"))
    industry_breadth = _num(industry.get("industry_breadth"), _num(metrics.get("industry_breadth")))
    top_industry_ratio = _num(industry.get("top_industry_ratio"), _num(metrics.get("top_industry_ratio")))
    structure_state = str(market_structure.get("state") or "")
    reasons: list[str] = []

    if structural_state != "STRUCTURAL_BULL_ROTATION":
        return {
            "applies": False,
            "source_structural_state": structural_state,
            "allocation_structural_state": structural_state,
            "risk_budget": None,
            "reasons": ["Source structural state is not STRUCTURAL_BULL_ROTATION."],
            "inputs": {
                "theme_risk_level": theme_risk_level,
                "crowding_score": round(crowding_score, 4),
                "quality_score": round(quality_score, 4),
            },
        }

    overheated = theme_risk_level == "high" or crowding_score >= 72 or quality_score < 45
    healthy = (
        theme_risk_level == "low"
        and crowding_score <= 48
        and quality_score >= 60
        and industry_strength >= 55
        and theme_persistence >= 75
    )
    broad_support = industry_breadth >= 0.45 or rotation_health >= 55 or structure_state == "BULL_BROADENING"

    if overheated:
        allocation_state = "STRUCTURAL_BULL_OVERHEATED"
        risk_budget = "medium"
        reasons.append("Theme risk, crowding or quality indicates overheated structural bull conditions.")
    elif healthy and broad_support:
        allocation_state = "STRUCTURAL_BULL_HEALTHY"
        risk_budget = "high"
        reasons.append("Theme persistence is strong, crowding is low and breadth/rotation support is sufficient.")
    elif healthy:
        allocation_state = "STRUCTURAL_BULL_HEALTHY"
        risk_budget = "medium_high"
        reasons.append("Theme persistence is strong and crowding is low, but breadth support is not broad enough for high.")
    else:
        allocation_state = "STRUCTURAL_BULL_BALANCED"
        risk_budget = "medium_high"
        reasons.append("Structural bull exists, but evidence is neither clearly healthy nor overheated.")

    return {
        "applies": True,
        "source_structural_state": structural_state,
        "allocation_structural_state": allocation_state,
        "risk_budget": risk_budget,
        "reasons": reasons,
        "inputs": {
            "theme_risk_level": theme_risk_level,
            "crowding_score": round(crowding_score, 4),
            "quality_score": round(quality_score, 4),
            "industry_strength": round(industry_strength, 4),
            "theme_persistence": round(theme_persistence, 4),
            "rotation_health": round(rotation_health, 4),
            "industry_breadth": round(industry_breadth, 4),
            "top_industry_ratio": round(top_industry_ratio, 4),
            "market_structure_state": structure_state,
        },
        "constraints": {
            "does_not_change_source_structural_state": True,
            "allocation_policy_only": True,
            "no_etf_selection": True,
            "no_single_stock": True,
            "no_trade_execution": True,
            "no_new_alpha_factor": True,
        },
    }
