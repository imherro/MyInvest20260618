from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping

from config import DATA_DIR
from style_allocation.historical_style_context import STYLE_CONTEXT_FIELDS
from style_allocation.structural_style_failure_analysis import (
    _read_structural_rows,
    structural_style_case_records,
)


DEFAULT_OUTPUT_PATH = DATA_DIR / "structural_style_context_attribution.json"
DEFAULT_STYLE_VALIDATION_PATH = DATA_DIR / "style_validation.json"
DEFAULT_CONTEXT_PATH = DATA_DIR / "historical_style_context.json"

NUMERIC_CONTEXT_FIELDS = (
    "industry_breadth",
    "positive_industry_ratio",
    "top_industry_ratio",
    "theme_persistence",
    "crowding_score",
    "price_extension",
    "trend",
    "breadth",
    "liquidity",
    "volatility",
    "pressure",
)


def _read_json(path: str | Path) -> dict[str, object]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(str(source))
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {source}")
    return payload


def _float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: Iterable[object]) -> float | None:
    numbers = [_float(value) for value in values]
    clean = [value for value in numbers if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


def _context_rows_by_date(payload: Mapping[str, object]) -> list[dict[str, object]]:
    rows = [dict(row) for row in payload.get("rows") or [] if isinstance(row, Mapping)]
    return sorted(rows, key=lambda row: str(row.get("date")))


def context_row_for_date(rows: list[Mapping[str, object]], date_text: str) -> Mapping[str, object] | None:
    result = None
    for row in rows:
        row_date = str(row.get("date") or "")
        if row_date > date_text:
            break
        result = row
    return result


def _lag_sessions(context_rows: list[Mapping[str, object]], context_date: str | None, signal_date: str) -> int | None:
    if context_date is None:
        return None
    dates = [str(row.get("date")) for row in context_rows if row.get("date")]
    try:
        return dates.index(signal_date) - dates.index(context_date)
    except ValueError:
        return None


def joined_context_records(
    observation_rows: list[Mapping[str, object]],
    context_rows: list[Mapping[str, object]],
    structural_rows: list[Mapping[str, object]],
) -> list[dict[str, object]]:
    records = structural_style_case_records(observation_rows, structural_rows)
    joined = []
    for record in records:
        signal_date = str(record.get("date"))
        context_row = context_row_for_date(context_rows, signal_date)
        context_date = None if context_row is None else str(context_row.get("date"))
        style_context = {} if context_row is None else dict(context_row.get("style_context") or {})
        joined.append(
            {
                **record,
                "context_date": context_date,
                "context_lag_sessions": _lag_sessions(context_rows, context_date, signal_date),
                "style_context": {
                    field: style_context.get(field)
                    for field in STYLE_CONTEXT_FIELDS
                },
                "context_available": context_row is not None,
                "context_future_safe": context_row is None or context_date <= signal_date,
                "context_missing_fields": [] if context_row is None else list((context_row.get("data_quality") or {}).get("missing_fields") or []),
            }
        )
    return joined


def _group_summary(records: list[Mapping[str, object]]) -> dict[str, object]:
    risk_distribution = Counter(str((record.get("style_context") or {}).get("theme_risk_level") or "unknown") for record in records)
    style_distribution = Counter(str(record.get("dominant_style") or "unknown") for record in records)
    return {
        "count": len(records),
        "mean_relative_to_baseline": _mean(record.get("relative_to_baseline") for record in records),
        "mean_baseline_return": _mean(record.get("baseline_return") for record in records),
        "mean_style_aware_return": _mean(record.get("style_aware_return") for record in records),
        "mean_style_ic": _mean(record.get("style_ic") for record in records),
        "dominant_style_distribution": dict(sorted(style_distribution.items())),
        "theme_risk_level_distribution": dict(sorted(risk_distribution.items())),
        "context_means": {
            field: _mean((record.get("style_context") or {}).get(field) for record in records)
            for field in NUMERIC_CONTEXT_FIELDS
        },
        "selection_diagnostics": {
            "baseline_style_overlap_count": _mean((record.get("derived") or {}).get("baseline_style_overlap_count") for record in records),
            "baseline_style_overlap_ratio": _mean((record.get("derived") or {}).get("baseline_style_overlap_ratio") for record in records),
            "style_score_margin": _mean((record.get("derived") or {}).get("style_score_margin") for record in records),
            "dominant_score": _mean((record.get("derived") or {}).get("dominant_score") for record in records),
        },
    }


def _difference(success: Mapping[str, object], failure: Mapping[str, object], source_key: str) -> dict[str, dict[str, object]]:
    success_values = success.get(source_key) or {}
    failure_values = failure.get(source_key) or {}
    result = {}
    for field in sorted(set(success_values) | set(failure_values)):
        success_mean = _float(success_values.get(field))
        failure_mean = _float(failure_values.get(field))
        gap = None
        if success_mean is not None and failure_mean is not None:
            gap = round(success_mean - failure_mean, 6)
        result[field] = {
            "success_mean": success_mean,
            "failure_mean": failure_mean,
            "success_minus_failure": gap,
        }
    return result


def _confidence(score: int, sample_count: int) -> str:
    if sample_count < 20:
        return "low"
    if score >= 3:
        return "medium"
    if score >= 1:
        return "low"
    return "not_supported"


def _gap(differences: Mapping[str, Mapping[str, object]], field: str) -> float | None:
    return _float((differences.get(field) or {}).get("success_minus_failure"))


def _hypotheses(
    context_differences: Mapping[str, Mapping[str, object]],
    selection_differences: Mapping[str, Mapping[str, object]],
    sample_count: int,
) -> list[dict[str, object]]:
    breadth_score = 0
    if (_gap(context_differences, "theme_persistence") or 0.0) > 5.0:
        breadth_score += 1
    if (_gap(context_differences, "industry_breadth") or 0.0) > 0.05:
        breadth_score += 1
    if (_gap(context_differences, "positive_industry_ratio") or 0.0) > 0.05:
        breadth_score += 1

    crowding_score = 0
    if (_gap(context_differences, "crowding_score") or 0.0) < -5.0:
        crowding_score += 1
    if (_gap(context_differences, "price_extension") or 0.0) < -5.0:
        crowding_score += 1
    if (_gap(context_differences, "industry_breadth") or 0.0) > 0.05:
        crowding_score += 1

    overlap_score = 0
    if (_gap(selection_differences, "baseline_style_overlap_count") or 0.0) < -0.2:
        overlap_score += 1
    if (_gap(selection_differences, "baseline_style_overlap_ratio") or 0.0) < -0.05:
        overlap_score += 1

    return [
        {
            "hypothesis": "success_needs_theme_persistence_and_industry_breadth",
            "finding": "structural_bull_style_works_better_when_theme_persistence_and_breadth_are_higher",
            "confidence": _confidence(breadth_score, sample_count),
            "support_score": breadth_score,
            "evidence_fields": {
                "theme_persistence": context_differences.get("theme_persistence"),
                "industry_breadth": context_differences.get("industry_breadth"),
                "positive_industry_ratio": context_differences.get("positive_industry_ratio"),
            },
        },
        {
            "hypothesis": "failure_when_single_theme_or_crowding_is_high",
            "finding": "structural_bull_style_fails_more_often_when_crowding_or_price_extension_is_higher",
            "confidence": _confidence(crowding_score, sample_count),
            "support_score": crowding_score,
            "evidence_fields": {
                "crowding_score": context_differences.get("crowding_score"),
                "price_extension": context_differences.get("price_extension"),
                "industry_breadth": context_differences.get("industry_breadth"),
            },
        },
        {
            "hypothesis": "failure_when_style_signal_has_low_incremental_information",
            "finding": "structural_bull_style_filter_adds_less_when_style_pool_overlaps_baseline",
            "confidence": _confidence(overlap_score, sample_count),
            "support_score": overlap_score,
            "evidence_fields": {
                "baseline_style_overlap_count": selection_differences.get("baseline_style_overlap_count"),
                "baseline_style_overlap_ratio": selection_differences.get("baseline_style_overlap_ratio"),
            },
        },
    ]


def _examples(records: list[Mapping[str, object]], case_type: str, limit: int = 5) -> list[dict[str, object]]:
    reverse = case_type == "success"
    ranked = sorted(
        [record for record in records if record.get("case_type") == case_type],
        key=lambda row: float(row.get("relative_to_baseline") or 0.0),
        reverse=reverse,
    )[:limit]
    return [
        {
            "date": record.get("date"),
            "context_date": record.get("context_date"),
            "dominant_style": record.get("dominant_style"),
            "baseline_return": record.get("baseline_return"),
            "style_aware_return": record.get("style_aware_return"),
            "relative_to_baseline": record.get("relative_to_baseline"),
            "style_context": record.get("style_context"),
            "selection_diagnostics": record.get("derived"),
        }
        for record in ranked
    ]


def analyze_context_records(records: list[Mapping[str, object]]) -> dict[str, object]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("case_type"))].append(record)
    success_records = list(grouped.get("success") or [])
    failure_records = list(grouped.get("failure") or [])
    success = _group_summary(success_records)
    failure = _group_summary(failure_records)
    context_differences = _difference(success, failure, "context_means")
    selection_differences = _difference(success, failure, "selection_diagnostics")
    sample_count = len(success_records) + len(failure_records)
    return {
        "case_counts": {
            "total": sample_count,
            "success": len(success_records),
            "failure": len(failure_records),
            "success_rate": None if sample_count == 0 else round(len(success_records) / sample_count, 6),
        },
        "success": success,
        "failure": failure,
        "context_differences": context_differences,
        "selection_differences": selection_differences,
        "hypothesis_tests": _hypotheses(context_differences, selection_differences, sample_count),
        "case_examples": {
            "success": _examples(records, "success"),
            "failure": _examples(records, "failure"),
        },
        "constraints": {
            "context_join_uses_same_day_or_prior_context": all(bool(record.get("context_future_safe")) for record in records),
            "future_returns_used_only_for_case_labels": True,
            "diagnostic_only": True,
        },
    }


def build_structural_style_context_attribution(
    *,
    style_validation_path: str | Path = DEFAULT_STYLE_VALIDATION_PATH,
    context_path: str | Path = DEFAULT_CONTEXT_PATH,
) -> dict[str, object]:
    style_validation = _read_json(style_validation_path)
    context_payload = _read_json(context_path)
    context_rows = _context_rows_by_date(context_payload)
    structural_rows = _read_structural_rows()
    results: dict[str, object] = {}
    for mode, horizon_rows in (style_validation.get("observations") or {}).items():
        results[mode] = {}
        for horizon, rows in (horizon_rows or {}).items():
            records = joined_context_records(list(rows or []), context_rows, structural_rows)
            results[mode][horizon] = analyze_context_records(records)
    tradable_20 = ((results.get("tradable_etf") or {}).get("20d") or {})
    tradable_60 = ((results.get("tradable_etf") or {}).get("60d") or {})
    return {
        "metadata": {
            "engine": "V3.5.6 Structural Bull Style Context Re-Attribution",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_style_validation_engine": (style_validation.get("metadata") or {}).get("engine"),
            "source_context_engine": (context_payload.get("metadata") or {}).get("engine"),
            "context_window": (context_payload.get("metadata") or {}).get("actual_window"),
            "validation_scope": "STRUCTURAL_BULL_CONTEXT_REATTRIBUTION",
        },
        "summary": {
            "edge_status_after_context_attribution": "diagnostic_only",
            "tradable_20d_case_counts": tradable_20.get("case_counts"),
            "tradable_60d_case_counts": tradable_60.get("case_counts"),
            "tradable_20d_hypotheses": tradable_20.get("hypothesis_tests"),
            "tradable_60d_hypotheses": tradable_60.get("hypothesis_tests"),
            "interpretation": (
                "This layer joins V3.5.5 historical context to V3.5.4 structural-bull success/failure samples. "
                "It is attribution only and does not produce style weights, allocation, or trades."
            ),
        },
        "results": results,
        "constraints": {
            "research_attribution_only": True,
            "uses_historical_style_context": True,
            "structural_bull_only": True,
            "context_join_uses_same_day_or_prior_context": True,
            "style_preference_formula_unchanged": True,
            "router_unchanged": True,
            "alpha_model_unchanged": True,
            "no_retraining": True,
            "no_parameter_optimization": True,
            "no_style_weight": True,
            "no_etf_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
        },
    }


def write_structural_style_context_attribution(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
