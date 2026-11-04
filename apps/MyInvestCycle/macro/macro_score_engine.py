from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev
from typing import Callable, Mapping

from macro.schema import MacroIndicatorRecord


QUALITY_WEIGHTS = {
    "valid": 1.0,
    "estimated": 0.8,
    "delayed": 0.6,
    "missing": 0.0,
    "invalid": 0.0,
}

COMPONENT_WEIGHTS = {
    "valuation": 0.30,
    "credit": 0.30,
    "economy": 0.20,
    "external": 0.20,
}

COMPONENT_INDICATORS = {
    "valuation": ("PE_percentile", "PB_percentile", "ERP"),
    "credit": ("M1_growth", "M2_growth", "social_financing_growth"),
    "economy": ("PMI", "CPI", "PPI"),
    "external": ("US10Y", "USD_CNH_offshore"),
}


@dataclass(frozen=True)
class IndicatorScore:
    indicator: str
    score: float | None
    value: float | None
    quality_weight: float
    observation_date: str | None
    release_date: str | None
    effective_date: str | None
    quality_status: str
    source: str | None
    explanation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "indicator": self.indicator,
            "score": None if self.score is None else round(self.score, 4),
            "value": self.value,
            "quality_weight": round(self.quality_weight, 4),
            "observation_date": self.observation_date,
            "release_date": self.release_date,
            "effective_date": self.effective_date,
            "quality_status": self.quality_status,
            "source": self.source,
            "explanation": self.explanation,
        }


def clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def band_score(value: float, low: float, target: float, high: float) -> float:
    if value <= low or value >= high:
        return 0.0
    if value == target:
        return 100.0
    if value < target:
        return clip((value - low) / (target - low) * 100.0)
    return clip((high - value) / (high - target) * 100.0)


def score_m1_growth(value: float) -> tuple[float, str]:
    score = clip(45.0 + value * 8.0)
    return score, "Higher M1 growth indicates improving transaction liquidity."


def score_m2_growth(value: float) -> tuple[float, str]:
    score = band_score(value, 2.0, 9.0, 16.0)
    return score, "Moderate M2 growth supports liquidity without overheating."


def score_social_financing_growth(value: float) -> tuple[float, str]:
    score = band_score(value, 2.0, 10.0, 18.0)
    return score, "Social financing stock growth measures broad credit expansion."


def score_pmi(value: float) -> tuple[float, str]:
    score = clip(50.0 + (value - 50.0) * 12.0)
    return score, "PMI above 50 indicates economic expansion."


def score_cpi(value: float) -> tuple[float, str]:
    score = band_score(value, -1.0, 2.0, 5.0)
    return score, "Moderate CPI is preferred; deflation or high inflation is penalized."


def score_ppi(value: float) -> tuple[float, str]:
    score = band_score(value, -5.0, 1.0, 8.0)
    return score, "PPI near mild positive growth indicates healthier industrial pricing."


def score_us10y(value: float) -> tuple[float, str]:
    score = clip(100.0 - max(0.0, value - 2.0) * 18.0)
    return score, "Higher US 10Y yield increases external discount-rate pressure."


def score_usd_cnh(value: float) -> tuple[float, str]:
    score = clip(100.0 - max(0.0, value - 6.5) * 45.0)
    return score, "Higher offshore USD/CNH indicates RMB depreciation pressure."


SCORERS: dict[str, Callable[[float], tuple[float, str]]] = {
    "M1_growth": score_m1_growth,
    "M2_growth": score_m2_growth,
    "social_financing_growth": score_social_financing_growth,
    "PMI": score_pmi,
    "CPI": score_cpi,
    "PPI": score_ppi,
    "US10Y": score_us10y,
    "USD_CNH_offshore": score_usd_cnh,
}


def score_indicator(indicator: str, record: MacroIndicatorRecord | None) -> IndicatorScore:
    if record is None:
        return IndicatorScore(
            indicator=indicator,
            score=None,
            value=None,
            quality_weight=0.0,
            observation_date=None,
            release_date=None,
            effective_date=None,
            quality_status="missing",
            source=None,
            explanation="No available time-safe record.",
        )
    if record.value is None or indicator not in SCORERS:
        return IndicatorScore(
            indicator=indicator,
            score=None,
            value=record.value,
            quality_weight=0.0,
            observation_date=record.observation_date,
            release_date=record.release_date,
            effective_date=record.effective_date,
            quality_status=record.quality_status,
            source=record.source,
            explanation="No scoring rule or usable value.",
        )

    score, explanation = SCORERS[indicator](float(record.value))
    return IndicatorScore(
        indicator=indicator,
        score=score,
        value=record.value,
        quality_weight=QUALITY_WEIGHTS.get(record.quality_status, 0.0),
        observation_date=record.observation_date,
        release_date=record.release_date,
        effective_date=record.effective_date,
        quality_status=record.quality_status,
        source=record.source,
        explanation=explanation,
    )


def component_score(indicator_scores: Mapping[str, IndicatorScore], indicators: tuple[str, ...]) -> dict[str, object]:
    weighted_sum = 0.0
    available_weight = 0.0
    used = []
    missing = []
    for indicator in indicators:
        item = indicator_scores.get(indicator)
        if item is None or item.score is None or item.quality_weight <= 0:
            missing.append(indicator)
            continue
        weighted_sum += float(item.score) * item.quality_weight
        available_weight += item.quality_weight
        used.append(indicator)

    return {
        "score": None if available_weight <= 0 else weighted_sum / available_weight,
        "available_weight": available_weight,
        "used_indicators": used,
        "missing_indicators": missing,
    }


def aggregate_macro_score(component_scores: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    weighted_sum = 0.0
    available_weight = 0.0
    configured_weight = sum(COMPONENT_WEIGHTS.values())
    available_scores = []

    for component, base_weight in COMPONENT_WEIGHTS.items():
        score = component_scores.get(component, {}).get("score")
        if score is None:
            continue
        weighted_sum += float(score) * base_weight
        available_weight += base_weight
        available_scores.append(float(score))

    macro_score = None if available_weight <= 0 else weighted_sum / available_weight
    coverage_ratio = 0.0 if configured_weight <= 0 else available_weight / configured_weight
    consistency = 1.0
    if len(available_scores) >= 2:
        consistency = clip(1.0 - pstdev(available_scores) / 50.0, 0.0, 1.0)

    return {
        "macro_score": macro_score,
        "available_component_weight": available_weight,
        "configured_component_weight": configured_weight,
        "coverage_ratio": coverage_ratio,
        "consistency": consistency,
    }
