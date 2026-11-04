from __future__ import annotations

from typing import Mapping

from allocation_policy.risk_budget_schema import (
    BUDGET_LEVELS,
    STYLE_BUDGET_RULES,
    STYLE_LABELS,
    STYLE_ROLES,
    budget_level_index,
    shift_budget_level,
    style_budget_universe_payload,
)


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


def _budget_max(left: str, right: str) -> str:
    return left if budget_level_index(left) >= budget_level_index(right) else right


def _budget_min(left: str, right: str) -> str:
    return left if budget_level_index(left) <= budget_level_index(right) else right


def _default_style_permissions() -> dict[str, dict[str, object]]:
    return {
        rule.style_id: {
            "style_id": rule.style_id,
            "label": rule.label,
            "role": rule.role,
            "allowed": rule.default_budget != "blocked",
            "budget_ceiling": rule.default_budget,
            "budget_floor": "blocked",
            "controls": [],
            "reasons": [f"default_budget={rule.default_budget}"],
        }
        for rule in STYLE_BUDGET_RULES
    }


def _cap_style(permissions: dict[str, dict[str, object]], style_id: str, cap: str, reason: str) -> None:
    row = permissions[style_id]
    row["budget_ceiling"] = _budget_min(str(row["budget_ceiling"]), cap)
    row["budget_floor"] = _budget_min(str(row["budget_floor"]), str(row["budget_ceiling"]))
    row["allowed"] = row["budget_ceiling"] != "blocked"
    row["reasons"].append(reason)


def _raise_style(permissions: dict[str, dict[str, object]], style_id: str, floor: str, reason: str) -> None:
    row = permissions[style_id]
    row["budget_floor"] = _budget_max(str(row["budget_floor"]), floor)
    row["budget_ceiling"] = _budget_max(str(row["budget_ceiling"]), floor)
    row["allowed"] = row["budget_ceiling"] != "blocked"
    row["reasons"].append(reason)


def _add_control(permissions: dict[str, dict[str, object]], style_id: str, control: str) -> None:
    controls = permissions[style_id]["controls"]
    if isinstance(controls, list) and control not in controls:
        controls.append(control)


def _dominant_style(style_preference: Mapping[str, object]) -> str | None:
    value = style_preference.get("dominant_style")
    return None if value is None else str(value)


def _style_scores(style_preference: Mapping[str, object]) -> dict[str, float]:
    environment = style_preference.get("style_environment") or {}
    result = {}
    if isinstance(environment, Mapping):
        for style_id, row in environment.items():
            if isinstance(row, Mapping):
                result[str(style_id)] = _num(row.get("preference_score"))
    return result


def _weak_style_alpha(edge_status: str) -> bool:
    return edge_status in {"weak_short_horizon_trace", "no_clear_incremental_edge", ""}


def build_style_constraints(inputs: Mapping[str, object]) -> dict[str, object]:
    macro = _section(inputs, "macro")
    structural = _section(inputs, "structural")
    market = _section(inputs, "market_structure")
    industry = _section(inputs, "industry_opportunity")
    theme_risk = _section(inputs, "theme_risk")
    style_preference = _section(inputs, "style_preference")
    style_incremental = _section(inputs, "style_incremental")

    macro_state = str(macro.get("state") or "UNKNOWN")
    structural_state = str(structural.get("state") or "UNKNOWN")
    market_state = str(market.get("state") or "UNKNOWN")
    theme_risk_level = str(theme_risk.get("level") or theme_risk.get("theme_risk_level") or "unknown")
    warnings = {str(item) for item in theme_risk.get("warnings") or []}
    edge_status = str(style_incremental.get("style_incremental_edge_status") or "")

    breadth = _num(market.get("breadth"))
    liquidity = _num(market.get("liquidity"))
    index_trend = _num(market.get("index_trend"))
    theme_persistence = _num(industry.get("theme_persistence"))
    industry_breadth = _num(industry.get("industry_breadth"))
    top_industry_ratio = _num(industry.get("top_industry_ratio"))
    crowding_score = _num(theme_risk.get("crowding_score"))
    quality_score = _num(theme_risk.get("quality_score"))
    dominant_style = _dominant_style(style_preference)
    style_scores = _style_scores(style_preference)

    permissions = _default_style_permissions()
    environment_reasons: list[str] = []

    if macro_state == "RECOVERY":
        _raise_style(permissions, "growth", "medium_high", "macro RECOVERY supports offensive beta budget.")
        _raise_style(permissions, "small_cap", "medium", "macro RECOVERY keeps small-cap beta observable.")
        environment_reasons.append("macro_recovery")
    elif macro_state in {"CONTRACTION", "BEAR", "STAGFLATION"}:
        _cap_style(permissions, "growth", "low", f"macro {macro_state} caps growth beta.")
        _cap_style(permissions, "small_cap", "low", f"macro {macro_state} caps small-cap beta.")
        _raise_style(permissions, "dividend", "medium_high", f"macro {macro_state} requires defensive beta.")
        environment_reasons.append(f"macro_{macro_state.lower()}_defensive")

    if structural_state == "STRUCTURAL_BULL_ROTATION":
        _raise_style(permissions, "growth", "medium_high", "structural bull rotation allows growth beta observation.")
        _raise_style(permissions, "small_cap", "medium", "structural bull rotation allows rotation beta observation.")
        environment_reasons.append("structural_bull_rotation")
    elif structural_state == "BROAD_BULL":
        _raise_style(permissions, "growth", "high", "broad bull allows high offensive beta budget.")
        _raise_style(permissions, "small_cap", "high", "broad bull allows high breadth beta budget.")
        environment_reasons.append("broad_bull")
    elif structural_state in {"BEAR_STRUCTURE", "WEAK_MARKET"}:
        _cap_style(permissions, "growth", "low", "weak structure caps growth beta.")
        _cap_style(permissions, "small_cap", "low", "weak structure caps small-cap beta.")
        _raise_style(permissions, "dividend", "high", "weak structure requires defensive beta.")
        environment_reasons.append("weak_structure_defensive")

    if market_state == "BULL_DIVERGENCE" or breadth < 25 or industry_breadth < 0.2:
        _cap_style(permissions, "small_cap", "medium", "narrow breadth prevents high small-cap budget.")
        _raise_style(permissions, "dividend", "medium", "narrow breadth requires defensive counterweight.")
        _add_control(permissions, "growth", "breadth_confirmation_required")
        _add_control(permissions, "small_cap", "breadth_confirmation_required")
        environment_reasons.append("narrow_breadth")

    if liquidity < 50:
        _cap_style(permissions, "growth", "medium_high", "liquidity below expansion level caps growth budget.")
        _cap_style(permissions, "small_cap", "medium", "liquidity below expansion level caps small-cap budget.")
        environment_reasons.append("liquidity_not_expanding")

    if theme_risk_level == "high" or crowding_score >= 72:
        _cap_style(permissions, "growth", "medium", "high crowding/theme risk caps growth budget.")
        _cap_style(permissions, "small_cap", "medium", "high crowding/theme risk caps small-cap budget.")
        _raise_style(permissions, "dividend", "medium_high", "high crowding/theme risk requires defensive beta.")
        _add_control(permissions, "growth", "crowding_control_required")
        environment_reasons.append("high_theme_risk")
    elif theme_risk_level == "medium":
        _cap_style(permissions, "growth", "medium_high", "medium theme risk prevents unrestricted growth budget.")
        _raise_style(permissions, "dividend", "medium", "medium theme risk keeps defensive beta available.")
        _add_control(permissions, "growth", "crowding_control_required")
        environment_reasons.append("medium_theme_risk")

    if top_industry_ratio >= 0.25:
        _add_control(permissions, "growth", "single_theme_concentration_watch")
        _cap_style(permissions, "growth", "medium_high", "top industry concentration caps single-theme growth budget.")
        environment_reasons.append("single_theme_concentration")

    if _weak_style_alpha(edge_status):
        for style_id in permissions:
            _add_control(permissions, style_id, "style_is_descriptor_not_alpha")
        environment_reasons.append("style_incremental_edge_weak")

    if dominant_style in permissions and _num(style_scores.get(dominant_style)) >= 70:
        _add_control(permissions, dominant_style, "dominant_style_requires_confirmation")
        permissions[dominant_style]["reasons"].append(
            "dominant style score is high, but V3.5.7 prevents using it as standalone alpha."
        )

    offensive_ceiling = _budget_min(
        str(permissions["growth"]["budget_ceiling"]),
        str(permissions["small_cap"]["budget_ceiling"]),
    )
    defensive_required = budget_level_index(str(permissions["dividend"]["budget_floor"])) >= budget_level_index("medium")
    risk_constraints = {
        "max_single_style_budget": "medium_high" if theme_risk_level in {"medium", "high"} or top_industry_ratio >= 0.25 else "high",
        "max_offensive_beta_budget": offensive_ceiling,
        "min_core_beta_budget": str(permissions["value"]["budget_floor"]),
        "min_defensive_beta_budget": str(permissions["dividend"]["budget_floor"]),
        "growth_budget_ceiling": str(permissions["growth"]["budget_ceiling"]),
        "small_cap_budget_ceiling": str(permissions["small_cap"]["budget_ceiling"]),
        "value_budget_ceiling": str(permissions["value"]["budget_ceiling"]),
        "dividend_budget_floor": str(permissions["dividend"]["budget_floor"]),
        "style_score_may_not_expand_budget_by_itself": _weak_style_alpha(edge_status),
        "requires_breadth_confirmation_for_offensive_expansion": "narrow_breadth" in environment_reasons,
        "requires_crowding_control": theme_risk_level in {"medium", "high"} or crowding_score >= 56,
    }
    allocation_environment = {
        "macro_state": macro_state,
        "structural_state": structural_state,
        "market_structure_state": market_state,
        "theme_risk_level": theme_risk_level,
        "dominant_style": dominant_style,
        "style_incremental_edge_status": edge_status or "unknown",
        "growth_allowed": bool(permissions["growth"]["allowed"]),
        "small_cap_allowed": bool(permissions["small_cap"]["allowed"]),
        "value_core_allowed": bool(permissions["value"]["allowed"]),
        "dividend_defensive_required": defensive_required,
        "offensive_beta_allowed": bool(permissions["growth"]["allowed"] or permissions["small_cap"]["allowed"]),
        "crowding_control_required": bool(risk_constraints["requires_crowding_control"]),
        "single_theme_concentration_watch": top_industry_ratio >= 0.25,
        "style_alpha_independent": not _weak_style_alpha(edge_status),
    }
    policy_state = "structural_bull_with_crowding_control"
    if structural_state in {"BEAR_STRUCTURE", "WEAK_MARKET"}:
        policy_state = "defensive_beta_policy"
    elif macro_state in {"CONTRACTION", "BEAR", "STAGFLATION"}:
        policy_state = "macro_defensive_policy"
    elif structural_state == "BROAD_BULL" and theme_risk_level == "low":
        policy_state = "broad_bull_beta_policy"
    elif _weak_style_alpha(edge_status):
        policy_state = "constraint_only_style_descriptor"

    return {
        "style_budget_universe": style_budget_universe_payload(),
        "allocation_environment": allocation_environment,
        "risk_constraints": risk_constraints,
        "style_permissions": permissions,
        "policy_state": policy_state,
        "policy_summary": _policy_summary(policy_state, allocation_environment, risk_constraints),
        "evidence": {
            "macro_score": macro.get("score"),
            "structural_score": structural.get("score"),
            "index_trend": round(index_trend, 4),
            "breadth": round(breadth, 4),
            "liquidity": round(liquidity, 4),
            "theme_persistence": round(theme_persistence, 4),
            "industry_breadth": round(industry_breadth, 4),
            "top_industry_ratio": round(top_industry_ratio, 4),
            "crowding_score": round(crowding_score, 4),
            "quality_score": round(quality_score, 4),
            "theme_warnings": sorted(warnings),
            "style_scores": {key: round(value, 4) for key, value in sorted(style_scores.items())},
        },
        "rule_trace": environment_reasons,
        "constraints": {
            "policy_constraint_only": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "style_preference_is_not_alpha": _weak_style_alpha(edge_status),
            "budget_levels_are_qualitative": tuple(BUDGET_LEVELS),
        },
    }


def _policy_summary(
    policy_state: str,
    allocation_environment: Mapping[str, object],
    risk_constraints: Mapping[str, object],
) -> str:
    if policy_state == "constraint_only_style_descriptor":
        return (
            "Style Preference is retained as a regime/style descriptor, not an alpha signal. "
            f"Offensive beta is allowed only within {risk_constraints.get('max_offensive_beta_budget')} budget and requires breadth/crowding checks."
        )
    if policy_state == "structural_bull_with_crowding_control":
        return (
            "Structural bull conditions allow offensive beta, but medium theme risk and narrow breadth require crowding control and defensive counterweight."
        )
    if policy_state == "broad_bull_beta_policy":
        return "Broad bull and low theme risk allow higher offensive beta budgets while keeping core beta available."
    if policy_state in {"defensive_beta_policy", "macro_defensive_policy"}:
        return "Weak macro or structure shifts the policy toward defensive beta and caps offensive beta budgets."
    return f"Policy state {policy_state} generated from macro={allocation_environment.get('macro_state')} and structural={allocation_environment.get('structural_state')}."
