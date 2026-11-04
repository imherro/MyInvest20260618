from __future__ import annotations

from typing import Mapping


STRUCTURAL_STATES = (
    "STRUCTURAL_BULL_ROTATION",
    "BROAD_BULL",
    "WEAK_MARKET",
    "BEAR_REBOUND",
    "BEAR_STRUCTURE",
    "RANGE",
)

MACRO_BULLISH = {"BULL", "RECOVERY", "BOTTOMING"}
MACRO_BEARISH = {"BEAR"}
STRUCTURE_BEARISH = {"BEAR_BREAKDOWN"}
STRUCTURE_REBOUND = {"BEAR_RALLY"}
STRUCTURE_BULLISH = {"BULL_BROADENING", "BULL_DIVERGENCE", "BULL_PULLBACK", "STRUCTURAL_BULL_ROTATION"}


def _float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def _input(payload: Mapping[str, object], section: str, name: str, default: object = None) -> object:
    item = payload.get(section)
    if isinstance(item, Mapping):
        return item.get(name, default)
    return default


def classify_structural_bull(payload: Mapping[str, object]) -> str:
    macro_state = str(_input(payload, "macro", "state", "RANGE"))
    macro_score = _float(_input(payload, "macro", "score", 50.0), 50.0)
    structure_state = str(_input(payload, "market_structure", "state", "RANGE_ACCUMULATION"))
    structure_score = _float(_input(payload, "market_structure", "score", 50.0), 50.0)
    structure_breadth = _float(_input(payload, "market_structure", "breadth", 50.0), 50.0)
    industry_strength = _float(_input(payload, "industry_opportunity", "industry_strength", 0.0))
    theme_persistence = _float(_input(payload, "industry_opportunity", "theme_persistence", 0.0))
    rotation_health = _float(_input(payload, "industry_opportunity", "rotation_health", 0.0))
    industry_breadth = _float(_input(payload, "industry_opportunity", "industry_breadth", 0.0))
    top_industry_ratio = _float(_input(payload, "industry_opportunity", "top_industry_ratio", 0.0))

    macro_supportive = macro_state in MACRO_BULLISH or (macro_state == "RANGE" and macro_score >= 50)
    market_not_breakdown = structure_state not in STRUCTURE_BEARISH and structure_score >= 38
    theme_is_real = theme_persistence >= 70 and industry_strength >= 52 and rotation_health >= 50 and top_industry_ratio >= 0.12

    if macro_state in MACRO_BEARISH and structure_state in STRUCTURE_BEARISH:
        return "BEAR_STRUCTURE"
    if structure_state in STRUCTURE_BEARISH and industry_strength < 45:
        return "BEAR_STRUCTURE"
    if structure_state in STRUCTURE_REBOUND and theme_is_real:
        return "BEAR_REBOUND"
    if structure_state == "BULL_BROADENING" and industry_breadth >= 0.35 and industry_strength >= 60:
        return "BROAD_BULL"
    if macro_supportive and market_not_breakdown and theme_is_real:
        return "STRUCTURAL_BULL_ROTATION"
    if (macro_state in MACRO_BEARISH or structure_score < 42) and industry_strength < 45:
        return "WEAK_MARKET"
    if structure_state in STRUCTURE_BULLISH and structure_breadth >= 50 and industry_strength >= 55:
        return "BROAD_BULL"
    return "RANGE"


def score_structural_bull(payload: Mapping[str, object]) -> float:
    macro_score = _float(_input(payload, "macro", "score", 50.0), 50.0)
    structure_score = _float(_input(payload, "market_structure", "score", 50.0), 50.0)
    industry_strength = _float(_input(payload, "industry_opportunity", "industry_strength", 0.0))
    theme_persistence = _float(_input(payload, "industry_opportunity", "theme_persistence", 0.0))
    rotation_health = _float(_input(payload, "industry_opportunity", "rotation_health", 0.0))
    return round(
        0.24 * macro_score
        + 0.24 * structure_score
        + 0.22 * industry_strength
        + 0.22 * theme_persistence
        + 0.08 * rotation_health,
        4,
    )


def estimate_structural_confidence(payload: Mapping[str, object], state: str) -> float:
    macro_confidence = _float(_input(payload, "macro", "confidence", 0.55), 0.55)
    structure_confidence = _float(_input(payload, "market_structure", "confidence", 0.55), 0.55)
    industry_strength = _float(_input(payload, "industry_opportunity", "industry_strength", 0.0))
    theme_persistence = _float(_input(payload, "industry_opportunity", "theme_persistence", 0.0))
    rotation_health = _float(_input(payload, "industry_opportunity", "rotation_health", 0.0))
    industry_breadth = _float(_input(payload, "industry_opportunity", "industry_breadth", 0.0))
    source_type = str(_input(payload, "industry_opportunity", "source_type", "unknown"))
    source_penalty = 0.08 if source_type == "etf_proxy" else 0.0

    if state == "STRUCTURAL_BULL_ROTATION":
        margins = [
            max(0.0, min(1.0, (industry_strength - 52.0) / 28.0)),
            max(0.0, min(1.0, (theme_persistence - 70.0) / 25.0)),
            max(0.0, min(1.0, (rotation_health - 50.0) / 30.0)),
        ]
        raw = 0.44 + 0.18 * macro_confidence + 0.16 * structure_confidence + 0.22 * (sum(margins) / len(margins))
    elif state == "BROAD_BULL":
        raw = 0.50 + min(industry_breadth, 0.8) * 0.25 + 0.12 * structure_confidence
    elif state in {"BEAR_STRUCTURE", "WEAK_MARKET"}:
        raw = 0.48 + 0.16 * structure_confidence + max(0.0, 50.0 - industry_strength) / 250.0
    elif state == "BEAR_REBOUND":
        raw = 0.45 + max(industry_strength, theme_persistence) / 320.0
    else:
        raw = 0.42 + abs(score_structural_bull(payload) - 50.0) / 260.0
    return round(max(0.0, min(1.0, raw - source_penalty)), 4)
