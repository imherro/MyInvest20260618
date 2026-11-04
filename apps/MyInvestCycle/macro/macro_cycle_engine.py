from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from macro.indicator_registry import get_all_indicators
from macro.macro_loader import DEFAULT_MACRO_DATA_DIR, load_macro_indicators
from macro.macro_score_engine import (
    COMPONENT_INDICATORS,
    aggregate_macro_score,
    component_score,
    score_indicator,
)
from macro.macro_state_classifier import classify_macro_state
from macro.macro_explainer import explain_macro_state
from macro.release_calendar import filter_available_records
from macro.schema import MacroIndicatorRecord, normalize_date


def _latest_available_record(
    records: Iterable[MacroIndicatorRecord],
    decision_date: str,
) -> MacroIndicatorRecord | None:
    available = filter_available_records(list(records), decision_date)
    if not available:
        return None
    return sorted(available, key=lambda item: (item.observation_date, item.release_date, item.effective_date))[-1]


def _data_quality(indicator_scores: dict[str, object], components: dict[str, dict[str, object]]) -> dict[str, object]:
    component_missing = sorted(
        {
            str(indicator)
            for payload in components.values()
            for indicator in payload.get("missing_indicators", [])
        }
    )
    component_used = sorted(
        {
            str(indicator)
            for payload in components.values()
            for indicator in payload.get("used_indicators", [])
        }
    )
    total = len(component_used) + len(component_missing)
    estimated = 0
    valid = 0
    used = 0
    latest_dates = {}
    registered_available_but_unscored = []
    registered_missing_but_unscored = []
    for indicator, item in indicator_scores.items():
        payload = item.to_dict()
        if payload["score"] is None:
            if payload["observation_date"] is None:
                registered_missing_but_unscored.append(indicator)
            else:
                registered_available_but_unscored.append(indicator)
            continue
        used += 1
        if payload["quality_status"] == "estimated":
            estimated += 1
        if payload["quality_status"] == "valid":
            valid += 1
        latest_dates[indicator] = {
            "observation_date": payload["observation_date"],
            "release_date": payload["release_date"],
            "effective_date": payload["effective_date"],
            "quality_status": payload["quality_status"],
            "source": payload["source"],
        }

    coverage_ratio = 0.0 if total <= 0 else used / total
    estimated_ratio = 0.0 if used <= 0 else estimated / used
    valid_ratio = 0.0 if used <= 0 else valid / used
    quality_ratio = 0.0 if used <= 0 else (valid + 0.8 * estimated) / used
    return {
        "total_indicators": total,
        "used_indicators": used,
        "used_indicator_names": component_used,
        "missing_indicators": component_missing,
        "registered_available_but_unscored": sorted(registered_available_but_unscored),
        "registered_missing_but_unscored": sorted(registered_missing_but_unscored),
        "coverage_ratio": round(coverage_ratio, 6),
        "estimated_ratio": round(estimated_ratio, 6),
        "valid_ratio": round(valid_ratio, 6),
        "quality_ratio": round(quality_ratio, 6),
        "latest_records": latest_dates,
    }


def _confidence(aggregate: dict[str, object], data_quality: dict[str, object]) -> float:
    coverage = float(aggregate.get("coverage_ratio") or 0.0)
    quality = float(data_quality.get("quality_ratio") or 0.0)
    consistency = float(aggregate.get("consistency") or 0.0)
    return max(0.0, min(1.0, 0.45 * coverage + 0.35 * quality + 0.20 * consistency))


def build_macro_cycle_snapshot(
    as_of: str | int,
    *,
    start_date: str | int = "20200101",
    data_dir: str | Path = DEFAULT_MACRO_DATA_DIR,
) -> dict[str, object]:
    decision_date = normalize_date(as_of)
    records_by_indicator = load_macro_indicators(
        get_all_indicators(),
        start_date,
        decision_date,
        data_dir=data_dir,
    )
    latest_records = {
        indicator: _latest_available_record(records, decision_date)
        for indicator, records in records_by_indicator.items()
    }
    indicator_scores = {
        indicator: score_indicator(indicator, record)
        for indicator, record in latest_records.items()
    }
    components = {
        component: component_score(indicator_scores, indicators)
        for component, indicators in COMPONENT_INDICATORS.items()
    }
    aggregate = aggregate_macro_score(components)
    macro_score = aggregate["macro_score"]
    macro_state = classify_macro_state(None if macro_score is None else float(macro_score), components)
    data_quality = _data_quality(indicator_scores, components)
    confidence = _confidence(aggregate, data_quality)
    explanation = explain_macro_state(
        macro_state=macro_state,
        macro_score=None if macro_score is None else float(macro_score),
        components=components,
        data_quality=data_quality,
    )

    return {
        "engine": "V2.2.1 Macro Cycle Engine Core",
        "as_of": decision_date,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "macro_state": macro_state,
        "macro_score": None if macro_score is None else round(float(macro_score), 4),
        "confidence": round(confidence, 4),
        "components": {
            name: {
                **payload,
                "score": None if payload["score"] is None else round(float(payload["score"]), 4),
            }
            for name, payload in components.items()
        },
        "indicator_scores": {
            indicator: score.to_dict()
            for indicator, score in indicator_scores.items()
        },
        "data_quality": data_quality,
        "explanation": explanation,
        "constraints": {
            "no_position_sizing": True,
            "no_etf_allocation": True,
            "no_trade_signal": True,
            "no_backtest": True,
            "uses_macro_data_foundation_only": True,
        },
    }
