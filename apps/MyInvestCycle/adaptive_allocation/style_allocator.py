from __future__ import annotations

from typing import Mapping


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def determine_style_preference(
    structural_payload: Mapping[str, object],
    theme_risk_payload: Mapping[str, object],
) -> list[str]:
    state = str(structural_payload.get("structural_state", "RANGE"))
    theme_risk_level = str(theme_risk_payload.get("theme_risk_level", "medium"))
    evidence = _section(structural_payload, "evidence")
    industry = _section(evidence, "industry_opportunity")
    theme_persistence = float(industry.get("theme_persistence") or 0.0)

    if state == "BROAD_BULL":
        styles = ["broad_beta", "growth", "mid_cap"]
    elif state == "STRUCTURAL_BULL_ROTATION":
        styles = ["industry_rotation", "growth", "relative_strength"]
    elif state == "BEAR_REBOUND":
        styles = ["rebound_quality", "risk_control", "cash_buffer"]
    elif state in {"BEAR_STRUCTURE", "WEAK_MARKET"}:
        styles = ["defensive", "low_volatility", "cash_buffer"]
    else:
        styles = ["balanced", "quality_value", "cash_buffer"]

    if theme_risk_level in {"medium", "high"} and "quality_filter" not in styles:
        styles.append("quality_filter")
    if theme_risk_level == "high" and "crowding_control" not in styles:
        styles.append("crowding_control")
    if theme_persistence >= 80 and "theme_persistence" not in styles:
        styles.append("theme_persistence")
    return styles
