from __future__ import annotations

from typing import Mapping, Sequence


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 4)


def _context(row: Mapping[str, object]) -> Mapping[str, object]:
    context = row.get("analysis_context")
    return context if isinstance(context, Mapping) else {}


def _number(row: Mapping[str, object], field: str) -> float | None:
    return _to_float(_context(row).get(field))


def _inverse(value: float | None) -> float | None:
    return None if value is None else _clamp(100.0 - value)


def _weighted(components: Sequence[tuple[str, float | None, float]]) -> tuple[float | None, list[dict[str, object]]]:
    used = [
        {"name": name, "value": value, "weight": weight}
        for name, value, weight in components
        if value is not None and weight > 0
    ]
    total_weight = sum(float(item["weight"]) for item in used)
    if not used or total_weight <= 0:
        return None, []
    score = sum(float(item["value"]) * float(item["weight"]) for item in used) / total_weight
    return round(score, 4), used


def _opportunity_state_score(value: object) -> float:
    scores = {
        "BULL_EXPANSION": 82.0,
        "STRUCTURAL_ROTATION": 68.0,
        "EARLY_RECOVERY": 58.0,
    }
    return scores.get(str(value or ""), 45.0)


def _market_phase_score(value: object) -> float:
    scores = {
        "EXPANSION": 80.0,
        "EARLY_CYCLE": 66.0,
        "ROTATION": 58.0,
        "LATE_CYCLE": 48.0,
        "CONTRACTION": 30.0,
    }
    return scores.get(str(value or ""), 45.0)


def _crowding_pressure(value: object) -> float:
    scores = {
        "CROWDED": 78.0,
        "NORMAL": 35.0,
        "LOW_RISK": 18.0,
    }
    return scores.get(str(value or ""), 45.0)


def exposure_context_scores(row: Mapping[str, object]) -> dict[str, object]:
    context = _context(row)
    participation_score, participation_components = _weighted(
        (
            ("macro_support", _number(row, "macro_score"), 0.16),
            ("trend_support", _number(row, "trend_score"), 0.14),
            ("breadth_support", _number(row, "breadth_score"), 0.14),
            ("liquidity_support", _number(row, "liquidity_score"), 0.12),
            ("industry_breadth", _number(row, "industry_breadth"), 0.12),
            ("theme_persistence", _number(row, "theme_persistence"), 0.10),
            ("opportunity_state", _opportunity_state_score(context.get("opportunity_state")), 0.12),
            ("market_phase", _market_phase_score(context.get("market_phase")), 0.10),
        )
    )
    protection_score, protection_components = _weighted(
        (
            ("risk_gradient", _to_float(row.get("risk_gradient_score")), 0.30),
            ("crowding_pressure", _crowding_pressure(context.get("risk_state")), 0.16),
            ("price_extension", _number(row, "price_extension_proxy"), 0.16),
            ("breadth_weakness", _inverse(_number(row, "breadth_score")), 0.12),
            ("liquidity_weakness", _inverse(_number(row, "liquidity_score")), 0.10),
            ("trend_weakness", _inverse(_number(row, "trend_score")), 0.08),
            ("volatility_weakness", _inverse(_number(row, "volatility_score")), 0.08),
        )
    )
    context_label = "neutral"
    if participation_score is not None and protection_score is not None:
        if participation_score >= 60 and protection_score >= 65:
            context_label = "protect_but_participate"
        elif participation_score >= 65 and protection_score < 65:
            context_label = "participation_favored"
        elif protection_score >= 65 and participation_score < 60:
            context_label = "protection_favored"
        elif participation_score < 45 and protection_score < 45:
            context_label = "wait_for_signal"
    return {
        "participation_score": participation_score,
        "protection_score": protection_score,
        "context_label": context_label,
        "participation_components": participation_components,
        "protection_components": protection_components,
        "research_only": True,
    }


def score_bucket(score: object) -> str:
    value = _to_float(score)
    if value is None:
        return "unknown"
    if value >= 65:
        return "high"
    if value >= 45:
        return "medium"
    return "low"
