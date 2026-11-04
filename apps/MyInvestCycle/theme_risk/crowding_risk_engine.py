from __future__ import annotations

from typing import Mapping


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        raise ValueError("high must be greater than low")
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def evaluate_crowding_risk(
    industry_payload: Mapping[str, object],
    valuation_items: list[Mapping[str, object]],
) -> dict[str, object]:
    themes = industry_payload.get("top_themes") or []
    metrics = industry_payload.get("metrics") or {}
    composites = [max(0.0, float(item.get("composite_score") or 0.0)) for item in themes if isinstance(item, Mapping)]
    total = sum(composites) or 1.0
    top1_contribution = composites[0] / total if composites else 0.0
    top3_contribution = sum(composites[:3]) / total if composites else 0.0
    industry_breadth = float(metrics.get("industry_breadth") or 0.0)
    positive_ratio = float(metrics.get("positive_industry_ratio") or 0.0)
    top_ratio = float(metrics.get("top_industry_ratio") or 0.0)
    pressure_values = [float(item.get("valuation_pressure_score") or 0.0) for item in valuation_items]
    average_pressure = sum(pressure_values[:3]) / min(3, len(pressure_values)) if pressure_values else 0.0

    concentration_score = 0.55 * _scale(top1_contribution, 0.16, 0.38) + 0.45 * _scale(top3_contribution, 0.40, 0.72)
    narrow_breadth_score = 100.0 - _scale(industry_breadth, 0.05, 0.35)
    weak_positive_score = 100.0 - _scale(positive_ratio, 0.20, 0.60)
    crowding_score = 0.36 * average_pressure + 0.30 * concentration_score + 0.22 * narrow_breadth_score + 0.12 * weak_positive_score
    warnings: list[str] = []
    if average_pressure >= 70:
        warnings.append("top_theme_price_extension_high")
    if concentration_score >= 65:
        warnings.append("theme_concentration_high")
    if narrow_breadth_score >= 70:
        warnings.append("industry_breadth_narrow")
    if top_ratio <= 0.18:
        warnings.append("few_industries_above_strength_threshold")

    return {
        "crowding_score": round(crowding_score, 4),
        "average_top_theme_pressure": round(average_pressure, 4),
        "top1_theme_contribution": round(top1_contribution, 4),
        "top3_theme_contribution": round(top3_contribution, 4),
        "concentration_score": round(concentration_score, 4),
        "breadth_quality": {
            "industry_breadth": round(industry_breadth, 4),
            "positive_industry_ratio": round(positive_ratio, 4),
            "top_industry_ratio": round(top_ratio, 4),
            "narrow_breadth_score": round(narrow_breadth_score, 4),
            "weak_positive_score": round(weak_positive_score, 4),
        },
        "warnings": warnings,
    }
