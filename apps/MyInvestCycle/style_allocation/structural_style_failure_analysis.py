from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping

from backtest.style_attribution_validation import DEFAULT_HORIZONS, TOP_N, build_style_validation
from config import DATA_DIR
from style_allocation.style_schema import STYLE_IDS
from style_allocation.style_validation import structural_row_for_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "structural_style_failure_analysis.json"

FEATURE_FIELDS = (
    "trend",
    "breadth",
    "liquidity",
    "volatility",
    "pressure",
    "momentum_decay",
    "liquidity_acceleration",
    "volatility_shock",
    "regime_persistence",
    "regime_score",
    "confidence",
)

REQUESTED_UNAVAILABLE_FIELDS = (
    "industry_breadth",
    "top_industry_ratio",
    "theme_persistence",
    "crowding_score",
    "price_extension",
    "theme_risk_level",
)


def _read_structural_rows(path: str | Path = DATA_DIR / "structural_hazard_dataset.json") -> list[dict[str, object]]:
    source = Path(path)
    if not source.exists():
        return []
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    rows = [dict(row) for row in payload if isinstance(row, Mapping)]
    return sorted(rows, key=lambda item: str(item.get("date")))


def _float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: Iterable[object]) -> float | None:
    clean = [_float(value) for value in values]
    numbers = [value for value in clean if value is not None]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 6)


def _style_score_diagnostics(row: Mapping[str, object]) -> dict[str, object]:
    scores = row.get("style_scores") or {}
    if not isinstance(scores, Mapping):
        scores = {}
    dominant_style = str(row.get("dominant_style") or "")
    dominant_score = _float(scores.get(dominant_style))
    sorted_scores = sorted(
        ((style_id, _float(scores.get(style_id)) or 0.0) for style_id in STYLE_IDS),
        key=lambda item: item[1],
        reverse=True,
    )
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else None
    total_score = sum(score for _, score in sorted_scores)
    margin = None
    concentration = None
    if dominant_score is not None and second_score is not None:
        margin = round(dominant_score - second_score, 6)
    if dominant_score is not None and total_score > 0:
        concentration = round(dominant_score / total_score, 6)
    forward_returns = row.get("style_forward_returns") or {}
    if not isinstance(forward_returns, Mapping):
        forward_returns = {}
    ranked_forward = sorted(
        (
            (style_id, _float(forward_returns.get(style_id)))
            for style_id in STYLE_IDS
            if _float(forward_returns.get(style_id)) is not None
        ),
        key=lambda item: item[1] if item[1] is not None else -999.0,
        reverse=True,
    )
    dominant_forward_rank = None
    best_future_style = None
    if ranked_forward:
        best_future_style = ranked_forward[0][0]
        for index, (style_id, _) in enumerate(ranked_forward, start=1):
            if style_id == dominant_style:
                dominant_forward_rank = index
                break
    return {
        "dominant_score": None if dominant_score is None else round(dominant_score, 6),
        "style_score_margin": margin,
        "style_score_concentration": concentration,
        "dominant_style_forward_rank": dominant_forward_rank,
        "best_future_style": best_future_style,
        "future_return_rank_is_validation_only": True,
    }


def structural_style_case_records(
    rows: list[Mapping[str, object]],
    structural_rows: list[Mapping[str, object]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in rows:
        if str(row.get("validation_state")) != "STRUCTURAL_BULL":
            continue
        relative = _float(row.get("relative_to_baseline"))
        if relative is None:
            continue
        structural_row = structural_row_for_date(structural_rows, str(row.get("date")))
        features = (structural_row or {}).get("features") or {}
        baseline_codes = [str(code) for code in row.get("baseline_codes") or []]
        style_codes = [str(code) for code in row.get("style_aware_codes") or []]
        overlap = len(set(baseline_codes) & set(style_codes))
        record = {
            "date": row.get("date"),
            "case_type": "success" if relative > 0 else "failure",
            "dominant_style": row.get("dominant_style"),
            "baseline_codes": baseline_codes,
            "style_aware_codes": style_codes,
            "baseline_return": row.get("baseline_return"),
            "style_aware_return": row.get("style_aware_return"),
            "relative_to_baseline": row.get("relative_to_baseline"),
            "style_ic": row.get("style_ic"),
            "style_scores": row.get("style_scores") or {},
            "style_forward_returns": row.get("style_forward_returns") or {},
            "features": {
                field: _float(features.get(field))
                for field in FEATURE_FIELDS
            },
            "derived": {
                "baseline_style_overlap_count": overlap,
                "baseline_style_overlap_ratio": round(overlap / len(style_codes), 6) if style_codes else None,
                **_style_score_diagnostics(row),
            },
        }
        records.append(record)
    return records


def _group_summary(records: list[Mapping[str, object]]) -> dict[str, object]:
    style_distribution = Counter(str(record.get("dominant_style")) for record in records)
    return {
        "count": len(records),
        "mean_relative_to_baseline": _mean(record.get("relative_to_baseline") for record in records),
        "mean_baseline_return": _mean(record.get("baseline_return") for record in records),
        "mean_style_aware_return": _mean(record.get("style_aware_return") for record in records),
        "mean_style_ic": _mean(record.get("style_ic") for record in records),
        "dominant_style_distribution": dict(sorted(style_distribution.items())),
        "feature_means": {
            field: _mean((record.get("features") or {}).get(field) for record in records)
            for field in FEATURE_FIELDS
        },
        "derived_means": {
            field: _mean((record.get("derived") or {}).get(field) for record in records)
            for field in (
                "baseline_style_overlap_count",
                "baseline_style_overlap_ratio",
                "dominant_score",
                "style_score_margin",
                "style_score_concentration",
                "dominant_style_forward_rank",
            )
        },
    }


def _difference_rows(success: Mapping[str, object], failure: Mapping[str, object], source_key: str) -> list[dict[str, object]]:
    success_values = success.get(source_key) or {}
    failure_values = failure.get(source_key) or {}
    rows = []
    for field in sorted(set(success_values) | set(failure_values)):
        success_mean = _float(success_values.get(field))
        failure_mean = _float(failure_values.get(field))
        difference = None
        if success_mean is not None and failure_mean is not None:
            difference = round(success_mean - failure_mean, 6)
        rows.append(
            {
                "field": field,
                "success_mean": success_mean,
                "failure_mean": failure_mean,
                "success_minus_failure": difference,
                "association": (
                    "higher_in_success"
                    if difference is not None and difference > 0
                    else "higher_in_failure"
                    if difference is not None and difference < 0
                    else "flat_or_unavailable"
                ),
            }
        )
    return rows


def _condition_candidates(differences: list[Mapping[str, object]], case_type: str, limit: int = 4) -> list[dict[str, object]]:
    validation_only_fields = {"dominant_style_forward_rank"}
    selected = []
    for row in differences:
        if str(row.get("field")) in validation_only_fields:
            continue
        diff = _float(row.get("success_minus_failure"))
        if diff is None or diff == 0:
            continue
        if case_type == "success" and diff <= 0:
            continue
        if case_type == "failure" and diff >= 0:
            continue
        selected.append(
            {
                "field": row.get("field"),
                "observed_direction": "higher" if (case_type == "success" and diff > 0) or (case_type == "failure" and diff < 0) else "lower",
                "absolute_gap": round(abs(diff), 6),
                "success_mean": row.get("success_mean"),
                "failure_mean": row.get("failure_mean"),
                "note": "Observed association inside STRUCTURAL_BULL validation samples; not a new rule or optimized threshold.",
            }
        )
    return sorted(selected, key=lambda item: float(item["absolute_gap"]), reverse=True)[:limit]


def _case_examples(records: list[Mapping[str, object]], case_type: str, limit: int = 5) -> list[dict[str, object]]:
    filtered = [record for record in records if record.get("case_type") == case_type]
    reverse = case_type == "success"
    ranked = sorted(
        filtered,
        key=lambda item: float(item.get("relative_to_baseline") or 0.0),
        reverse=reverse,
    )[:limit]
    examples = []
    for record in ranked:
        examples.append(
            {
                "date": record.get("date"),
                "dominant_style": record.get("dominant_style"),
                "baseline_codes": record.get("baseline_codes"),
                "style_aware_codes": record.get("style_aware_codes"),
                "baseline_return": record.get("baseline_return"),
                "style_aware_return": record.get("style_aware_return"),
                "relative_to_baseline": record.get("relative_to_baseline"),
                "style_ic": record.get("style_ic"),
                "features": record.get("features"),
                "derived": record.get("derived"),
            }
        )
    return examples


def analyze_structural_style_failures(rows: list[Mapping[str, object]], structural_rows: list[Mapping[str, object]]) -> dict[str, object]:
    records = structural_style_case_records(rows, structural_rows)
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("case_type"))].append(record)
    success_summary = _group_summary(list(grouped.get("success") or []))
    failure_summary = _group_summary(list(grouped.get("failure") or []))
    feature_differences = _difference_rows(success_summary, failure_summary, "feature_means")
    derived_differences = _difference_rows(success_summary, failure_summary, "derived_means")
    success_candidates = _condition_candidates(feature_differences + derived_differences, "success")
    failure_candidates = _condition_candidates(feature_differences + derived_differences, "failure")
    count = len(records)
    success_count = len(grouped.get("success") or [])
    return {
        "case_counts": {
            "total": count,
            "success": success_count,
            "failure": len(grouped.get("failure") or []),
            "success_rate": None if count == 0 else round(success_count / count, 6),
        },
        "success": success_summary,
        "failure": failure_summary,
        "feature_differences": feature_differences,
        "derived_differences": derived_differences,
        "condition_candidates": {
            "candidate_source": "signal_date_features_and_same_day_selection_diagnostics_only",
            "success_associations": success_candidates,
            "failure_associations": failure_candidates,
        },
        "case_examples": {
            "largest_success_spreads": _case_examples(records, "success"),
            "largest_failure_spreads": _case_examples(records, "failure"),
        },
        "interpretation": (
            "Success means style-aware return was above the all-asset Opportunity TopN baseline on that validation date. "
            "Associations are descriptive attribution only and do not create new thresholds, weights, or trades."
        ),
    }


def _summary_read(results: Mapping[str, object]) -> dict[str, object]:
    tradable_20 = ((results.get("tradable_etf") or {}).get("20d") or {})
    tradable_60 = ((results.get("tradable_etf") or {}).get("60d") or {})
    return {
        "edge_status_after_failure_attribution": "diagnostic_only",
        "tradable_20d_case_counts": tradable_20.get("case_counts"),
        "tradable_60d_case_counts": tradable_60.get("case_counts"),
        "tradable_20d_success_associations": (tradable_20.get("condition_candidates") or {}).get("success_associations") or [],
        "tradable_20d_failure_associations": (tradable_20.get("condition_candidates") or {}).get("failure_associations") or [],
        "tradable_60d_success_associations": (tradable_60.get("condition_candidates") or {}).get("success_associations") or [],
        "tradable_60d_failure_associations": (tradable_60.get("condition_candidates") or {}).get("failure_associations") or [],
        "interpretation": (
            "V3.5.4 explains the V3.5.3 positive-spread-not-robust result. "
            "It is a diagnostic layer and does not authorize V3.6 allocation."
        ),
    }


def build_structural_style_failure_analysis(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    step_sessions: int = 20,
    top_n: int = TOP_N,
) -> dict[str, object]:
    base = build_style_validation(
        start_date=start_date,
        end_date=end_date,
        horizons=horizons,
        step_sessions=step_sessions,
        top_n=top_n,
    )
    structural_rows = _read_structural_rows()
    results: dict[str, object] = {}
    for mode, horizon_rows in (base.get("observations") or {}).items():
        results[mode] = {}
        for horizon, rows in (horizon_rows or {}).items():
            results[mode][horizon] = analyze_structural_style_failures(rows, structural_rows)

    return {
        "metadata": {
            "engine": "V3.5.4 Structural Bull Style Failure Attribution",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": base["metadata"]["window"],
            "source_engine": base["metadata"]["engine"],
            "score_date_count": base["metadata"]["score_date_count"],
            "step_sessions": step_sessions,
            "horizons": list(horizons),
            "top_n": top_n,
            "validation_scope": "STRUCTURAL_BULL_SUCCESS_FAILURE_ATTRIBUTION",
        },
        "summary": _summary_read(results),
        "results": results,
        "field_coverage": {
            "available_historical_fields": list(FEATURE_FIELDS),
            "requested_but_unavailable_historical_fields": list(REQUESTED_UNAVAILABLE_FIELDS),
            "coverage_note": (
                "The current historical structural dataset does not carry industry breadth, theme persistence, "
                "crowding, price extension, or theme risk fields per validation date. These are marked unavailable "
                "instead of inferred from current snapshots."
            ),
        },
        "constraints": {
            "research_attribution_only": True,
            "structural_bull_only": True,
            "uses_v3_5_2_observations": True,
            "style_preference_formula_unchanged": True,
            "decision_inputs_only_use_same_day_or_prior_data": True,
            "future_returns_used_only_for_case_labels_and_attribution": True,
            "no_future_function_in_signal": True,
            "no_style_weight": True,
            "no_etf_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization": True,
            "failure_result_is_acceptable": True,
        },
    }


def write_structural_style_failure_analysis(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
