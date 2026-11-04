from __future__ import annotations

from typing import Mapping


STRUCTURE_STATES = (
    "BULL_BROADENING",
    "BULL_DIVERGENCE",
    "BULL_PULLBACK",
    "STRUCTURAL_BULL_ROTATION",
    "BEAR_RALLY",
    "BEAR_BREAKDOWN",
    "RANGE_ACCUMULATION",
)


def _metric(metrics: Mapping[str, object], name: str, default: float = 50.0) -> float:
    value = metrics.get(name)
    if value is None:
        return default
    return float(value)


def classify_structure(metrics: Mapping[str, object]) -> str:
    index_trend = _metric(metrics, "index_trend")
    breadth = _metric(metrics, "breadth")
    liquidity = _metric(metrics, "liquidity")
    pullback_health = _metric(metrics, "pullback_health")
    industry_strength = metrics.get("industry_strength")
    theme_persistence = metrics.get("theme_persistence")

    if (
        38 <= index_trend <= 68
        and industry_strength is not None
        and float(industry_strength) >= 75
        and theme_persistence is not None
        and float(theme_persistence) >= 60
        and breadth >= 35
    ):
        return "STRUCTURAL_BULL_ROTATION"

    if index_trend >= 70 and breadth >= 55 and liquidity >= 45:
        return "BULL_BROADENING"
    if index_trend >= 68 and breadth < 45:
        return "BULL_DIVERGENCE"
    if index_trend >= 58 and pullback_health < 50 and breadth >= 35:
        return "BULL_PULLBACK"
    if index_trend <= 35 and breadth <= 40 and liquidity <= 50:
        return "BEAR_BREAKDOWN"
    if index_trend <= 45 and (breadth >= 55 or liquidity >= 60):
        return "BEAR_RALLY"
    return "RANGE_ACCUMULATION"


def estimate_structure_confidence(metrics: Mapping[str, object], state: str) -> float:
    index_trend = _metric(metrics, "index_trend")
    breadth = _metric(metrics, "breadth")
    liquidity = _metric(metrics, "liquidity")
    structure_score = _metric(metrics, "structure_score")
    missing_count = len(metrics.get("missing_inputs") or [])
    data_penalty = min(0.25, missing_count * 0.06)

    if state == "BULL_BROADENING":
        raw = 0.50 + min(index_trend, breadth, liquidity) / 220.0
    elif state == "BULL_DIVERGENCE":
        raw = 0.50 + max(0.0, index_trend - breadth) / 120.0
    elif state == "BULL_PULLBACK":
        raw = 0.52 + max(0.0, index_trend - 55.0) / 150.0
    elif state == "STRUCTURAL_BULL_ROTATION":
        raw = 0.55 + float(metrics.get("industry_strength") or 0.0) / 250.0
    elif state == "BEAR_BREAKDOWN":
        raw = 0.52 + max(0.0, 50.0 - index_trend) / 130.0
    elif state == "BEAR_RALLY":
        raw = 0.45 + max(breadth, liquidity) / 260.0
    else:
        raw = 0.38 + (100.0 - abs(structure_score - 50.0)) / 220.0
    return round(max(0.0, min(1.0, raw - data_penalty)), 4)
