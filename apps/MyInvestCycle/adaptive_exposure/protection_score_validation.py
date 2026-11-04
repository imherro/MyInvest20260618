from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "protection_score_validation.json"

PROTECTION_BUCKETS = ("high", "medium", "low", "unknown")
RISK_BUCKETS = ("high_risk", "medium_risk", "low_risk", "unknown")
COMBINED_BUCKETS = (
    "both_high",
    "protection_only",
    "risk_gradient_only",
    "mixed_medium",
    "low_or_unflagged",
    "unknown",
)
FOCUS_PHASES = ("EARLY_CYCLE", "ROTATION", "LATE_CYCLE", "CONTRACTION")


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _date_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text if len(text) == 8 and text.isdigit() else None


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _flag(row: Mapping[str, object], key: str) -> bool:
    flags = row.get("future_flags")
    return bool(isinstance(flags, Mapping) and flags.get(key))


def _has_contradiction(row: Mapping[str, object]) -> bool:
    contradictions = row.get("contradictions")
    return isinstance(contradictions, list) and len(contradictions) > 0


def _context(row: Mapping[str, object]) -> Mapping[str, object]:
    context = row.get("analysis_context")
    return context if isinstance(context, Mapping) else {}


def _phase(row: Mapping[str, object]) -> str:
    return str(_context(row).get("market_phase") or row.get("market_phase") or "unknown")


def _combined_bucket(row: Mapping[str, object]) -> str:
    risk = str(row.get("risk_gradient_bucket") or "unknown")
    protection = str(row.get("protection_bucket") or "unknown")
    if risk == "unknown" or protection == "unknown":
        return "unknown"
    high_risk = risk == "high_risk"
    high_protection = protection == "high"
    if high_risk and high_protection:
        return "both_high"
    if high_protection:
        return "protection_only"
    if high_risk:
        return "risk_gradient_only"
    if risk == "medium_risk" or protection == "medium":
        return "mixed_medium"
    return "low_or_unflagged"


def _joined_rows(
    context_rows: Sequence[Mapping[str, object]],
    exposure_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    exposure_by_date = {str(row.get("date") or ""): row for row in exposure_rows}
    rows: list[dict[str, object]] = []
    for context_row in context_rows:
        date = _date_text(context_row.get("date"))
        if not date:
            continue
        exposure_row = exposure_by_date.get(date, {})
        contradictions = exposure_row.get("contradictions") if isinstance(exposure_row, Mapping) else []
        row = {
            "date": date,
            "market_phase": _phase(context_row),
            "opportunity_state": _context(context_row).get("opportunity_state"),
            "risk_state": _context(context_row).get("risk_state"),
            "risk_gradient_score": context_row.get("risk_gradient_score"),
            "risk_gradient_bucket": context_row.get("risk_gradient_bucket"),
            "protection_score": context_row.get("protection_score"),
            "protection_bucket": context_row.get("protection_bucket"),
            "combined_bucket": _combined_bucket(context_row),
            "future_environment": context_row.get("future_environment"),
            "future_flags": context_row.get("future_flags") or {},
            "contradictions": contradictions if isinstance(contradictions, list) else [],
            "source_context_label": context_row.get("context_label"),
            "source_trace": context_row.get("source_trace") or {},
            "data_quality": context_row.get("gradient_data_quality") or {},
        }
        rows.append(row)
    return rows


def _score_stats(rows: Sequence[Mapping[str, object]], field: str) -> dict[str, object]:
    values = [_to_float(row.get(field)) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return {"available_count": 0, "avg": None, "min": None, "max": None}
    return {
        "available_count": len(values),
        "avg": round(mean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _metrics(rows: Sequence[Mapping[str, object]], total_rows: int) -> dict[str, object]:
    high_risk_events = sum(1 for row in rows if _flag(row, "high_risk_event"))
    drawdown_events = sum(1 for row in rows if _flag(row, "future_drawdown_gt_15"))
    contradiction_rows = sum(1 for row in rows if _has_contradiction(row))
    return {
        "sample_count": len(rows),
        "sample_share": _share(len(rows), total_rows),
        "future_high_risk_count": high_risk_events,
        "future_high_risk_rate": _share(high_risk_events, len(rows)),
        "drawdown_event_count": drawdown_events,
        "drawdown_event_rate": _share(drawdown_events, len(rows)),
        "contradiction_count": contradiction_rows,
        "contradiction_rate": _share(contradiction_rows, len(rows)),
        "future_environment_distribution": _distribution(row.get("future_environment") for row in rows),
        "market_phase_distribution": _distribution(row.get("market_phase") for row in rows),
        "risk_gradient_score": _score_stats(rows, "risk_gradient_score"),
        "protection_score": _score_stats(rows, "protection_score"),
        "sample_rows": [
            {
                "date": row.get("date"),
                "market_phase": row.get("market_phase"),
                "risk_gradient_bucket": row.get("risk_gradient_bucket"),
                "protection_bucket": row.get("protection_bucket"),
                "combined_bucket": row.get("combined_bucket"),
                "future_environment": row.get("future_environment"),
                "future_high_risk_event": _flag(row, "high_risk_event"),
                "drawdown_event": _flag(row, "future_drawdown_gt_15"),
                "contradiction": _has_contradiction(row),
            }
            for row in rows[:8]
        ],
    }


def _bucket_metrics(
    rows: Sequence[Mapping[str, object]],
    *,
    field: str,
    buckets: Sequence[str],
) -> dict[str, dict[str, object]]:
    return {
        bucket: _metrics([row for row in rows if row.get(field) == bucket], len(rows))
        for bucket in buckets
    }


def _overall_metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return _metrics(rows, len(rows))


def _model_summary(
    rows: Sequence[Mapping[str, object]],
    *,
    model_id: str,
    bucket_field: str,
    high_bucket: str,
    bucket_metrics: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    overall = _overall_metrics(rows)
    high = bucket_metrics.get(high_bucket, {})
    high_count = int(high.get("sample_count") or 0)
    total_high_risk_events = int(overall.get("future_high_risk_count") or 0)
    high_group_events = int(high.get("future_high_risk_count") or 0)
    return {
        "model_id": model_id,
        "bucket_field": bucket_field,
        "high_bucket": high_bucket,
        "high_group_sample_count": high_count,
        "high_group_sample_share": _share(high_count, len(rows)),
        "high_group_high_risk_rate": high.get("future_high_risk_rate"),
        "high_group_drawdown_event_rate": high.get("drawdown_event_rate"),
        "high_group_contradiction_rate": high.get("contradiction_rate"),
        "high_group_high_risk_lift": round(float(high.get("future_high_risk_rate") or 0.0) - float(overall.get("future_high_risk_rate") or 0.0), 6),
        "high_group_drawdown_lift": round(float(high.get("drawdown_event_rate") or 0.0) - float(overall.get("drawdown_event_rate") or 0.0), 6),
        "high_group_contradiction_lift": round(float(high.get("contradiction_rate") or 0.0) - float(overall.get("contradiction_rate") or 0.0), 6),
        "high_risk_event_capture_rate": _share(high_group_events, total_high_risk_events),
        "false_warning_rate": _share(high_count - high_group_events, high_count),
    }


def _status(total_rows: int, high_rows: int, lift: float | None) -> str:
    if total_rows < 6:
        return "insufficient_total_sample"
    if high_rows < 3:
        return "insufficient_high_bucket_sample"
    if lift is None:
        return "insufficient_high_bucket_sample"
    if lift >= 0.05:
        return "positive"
    if lift <= -0.05:
        return "negative"
    return "flat"


def _phase_model_summary(
    rows: Sequence[Mapping[str, object]],
    *,
    bucket_field: str,
    high_bucket: str,
) -> dict[str, object]:
    metrics = _bucket_metrics(rows, field=bucket_field, buckets=(high_bucket,))
    high = metrics.get(high_bucket, {})
    overall = _overall_metrics(rows)
    lift = round(float(high.get("future_high_risk_rate") or 0.0) - float(overall.get("future_high_risk_rate") or 0.0), 6) if high else None
    return {
        "high_bucket": high_bucket,
        "high_sample_count": int(high.get("sample_count") or 0),
        "future_high_risk_rate": high.get("future_high_risk_rate"),
        "drawdown_event_rate": high.get("drawdown_event_rate"),
        "contradiction_rate": high.get("contradiction_rate"),
        "high_risk_lift": lift,
        "status": _status(len(rows), int(high.get("sample_count") or 0), lift),
    }


def _phase_analysis(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for phase in FOCUS_PHASES:
        phase_rows = [row for row in rows if row.get("market_phase") == phase]
        payload.append(
            {
                "market_phase": phase,
                "sample_count": len(phase_rows),
                "overall": _overall_metrics(phase_rows),
                "model_a_risk_gradient": _phase_model_summary(
                    phase_rows,
                    bucket_field="risk_gradient_bucket",
                    high_bucket="high_risk",
                ),
                "model_b_protection_score": _phase_model_summary(
                    phase_rows,
                    bucket_field="protection_bucket",
                    high_bucket="high",
                ),
                "model_c_combined": _phase_model_summary(
                    phase_rows,
                    bucket_field="combined_bucket",
                    high_bucket="both_high",
                ),
            }
        )
    return payload


def _phase_consistency(phase_rows: Sequence[Mapping[str, object]], model_key: str) -> dict[str, object]:
    statuses = [str(row.get(model_key, {}).get("status") or "unknown") for row in phase_rows]
    evaluated = [status for status in statuses if status in {"positive", "negative", "flat"}]
    positive = [status for status in evaluated if status == "positive"]
    negative = [status for status in evaluated if status == "negative"]
    flat = [status for status in evaluated if status == "flat"]
    insufficient = [status for status in statuses if status.startswith("insufficient")]
    if len(evaluated) < 2:
        consistency = "insufficient_evidence"
    elif len(negative) == 0 and _share(len(positive), len(evaluated)) >= 0.75:
        consistency = "high"
    elif len(negative) <= 1 and _share(len(positive), len(evaluated)) >= 0.5:
        consistency = "medium"
    else:
        consistency = "weak"
    return {
        "model_key": model_key,
        "phase_consistency": consistency,
        "evaluated_phase_count": len(evaluated),
        "positive_phase_count": len(positive),
        "negative_phase_count": len(negative),
        "flat_phase_count": len(flat),
        "insufficient_phase_count": len(insufficient),
    }


def _time_safety(rows: Sequence[Mapping[str, object]], context_source: Mapping[str, object]) -> dict[str, object]:
    violations = [
        {"date": row.get("date"), **violation}
        for row in rows
        for violation in ((row.get("data_quality") or {}).get("time_safety_violations") or [])
    ]
    source_time_safety = context_source.get("time_safety") if isinstance(context_source.get("time_safety"), Mapping) else {}
    return {
        "feature_release_or_source_lte_signal_date": not violations and bool(source_time_safety.get("feature_release_or_source_lte_signal_date", True)),
        "violation_count": len(violations) + int(source_time_safety.get("violation_count") or 0),
        "violation_examples": violations[:10],
        "future_labels_used_for_validation_only": True,
        "protection_score_is_precomputed_v6_3": True,
        "risk_gradient_is_precomputed_v5_10": True,
    }


def _threshold_audit(robustness_source: Mapping[str, object]) -> dict[str, object]:
    threshold = robustness_source.get("threshold_consistency")
    if not isinstance(threshold, Mapping):
        return {
            "available": False,
            "fixed_thresholds_reused_from_v5_11": True,
            "mismatch_count": None,
            "thresholds_were_not_optimized": True,
        }
    return {
        "available": True,
        "fixed_thresholds": threshold.get("fixed_thresholds"),
        "checked_rows": threshold.get("checked_rows"),
        "mismatch_count": threshold.get("mismatch_count"),
        "mismatch_examples": threshold.get("mismatch_examples", [])[:10],
        "fixed_thresholds_reused_from_v5_11": True,
        "thresholds_were_not_optimized": bool(threshold.get("thresholds_were_not_optimized", True)),
    }


def _comparison_summary(model_a: Mapping[str, object], model_b: Mapping[str, object], model_c: Mapping[str, object]) -> dict[str, object]:
    protection_minus_risk = round(float(model_b.get("high_group_high_risk_lift") or 0.0) - float(model_a.get("high_group_high_risk_lift") or 0.0), 6)
    combined_minus_protection = round(float(model_c.get("high_group_high_risk_lift") or 0.0) - float(model_b.get("high_group_high_risk_lift") or 0.0), 6)
    return {
        "protection_minus_risk_gradient_high_risk_lift": protection_minus_risk,
        "combined_minus_protection_high_risk_lift": combined_minus_protection,
        "protection_capture_rate": model_b.get("high_risk_event_capture_rate"),
        "risk_gradient_capture_rate": model_a.get("high_risk_event_capture_rate"),
        "combined_capture_rate": model_c.get("high_risk_event_capture_rate"),
        "protection_false_warning_rate": model_b.get("false_warning_rate"),
        "risk_gradient_false_warning_rate": model_a.get("false_warning_rate"),
        "combined_false_warning_rate": model_c.get("false_warning_rate"),
        "primary_read": (
            "Protection score improves coverage if it captures more high-risk events without materially increasing false warnings; "
            "combined context is stricter and should be read as a precision check, not a policy rule."
        ),
    }


def _review_items(
    model_b: Mapping[str, object],
    protection_consistency: Mapping[str, object],
    threshold: Mapping[str, object],
    time_safety: Mapping[str, object],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append({"type": "time_safety_violation", "severity": "high", "evidence": {"violation_count": time_safety.get("violation_count")}})
    if threshold.get("mismatch_count") not in {0, None}:
        items.append({"type": "risk_threshold_mismatch", "severity": "high", "evidence": {"mismatch_count": threshold.get("mismatch_count")}})
    if float(model_b.get("high_group_high_risk_lift") or 0.0) < 0.05:
        items.append({"type": "protection_score_high_bucket_risk_lift_weak", "severity": "high", "evidence": {"risk_lift": model_b.get("high_group_high_risk_lift")}})
    if protection_consistency.get("phase_consistency") in {"insufficient_evidence", "weak"}:
        items.append(
            {
                "type": "protection_score_phase_consistency_not_confirmed",
                "severity": "high",
                "evidence": {
                    "phase_consistency": protection_consistency.get("phase_consistency"),
                    "positive_phase_count": protection_consistency.get("positive_phase_count"),
                    "negative_phase_count": protection_consistency.get("negative_phase_count"),
                    "insufficient_phase_count": protection_consistency.get("insufficient_phase_count"),
                },
            }
        )
    items.append(
        {
            "type": "protection_validation_research_only_do_not_modify_exposure",
            "severity": "high",
            "evidence": {"reason": "V6.4 validates precomputed V6.3 protection score only; no bucket, mapper, exposure, ETF, weight, or trade change."},
        }
    )
    return items


def _conclusion(model_b: Mapping[str, object], protection_consistency: Mapping[str, object]) -> str:
    if float(model_b.get("high_group_high_risk_lift") or 0.0) < 0.05:
        return "protection_score_edge_not_confirmed"
    if protection_consistency.get("phase_consistency") in {"high", "medium"}:
        return "protection_score_research_value_confirmed_not_policy_ready"
    return "protection_score_signal_visible_but_not_robust"


def build_protection_score_validation(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    context_source = _read_json(root / "exposure_context_score_audit.json")
    exposure_source = _read_json(root / "exposure_simulation.json")
    robustness_source = _read_json(root / "risk_gradient_robustness.json")
    if not isinstance(context_source, Mapping) or not isinstance(context_source.get("rows"), list):
        raise RuntimeError("exposure_context_score_audit.json is missing or incomplete.")
    if not isinstance(exposure_source, Mapping) or not isinstance(exposure_source.get("historical_replay"), list):
        raise RuntimeError("exposure_simulation.json is missing or incomplete.")
    if not isinstance(robustness_source, Mapping):
        robustness_source = {}

    rows = _joined_rows(
        [row for row in context_source.get("rows") or [] if isinstance(row, Mapping)],
        [row for row in exposure_source.get("historical_replay") or [] if isinstance(row, Mapping)],
    )
    risk_bucket_metrics = _bucket_metrics(rows, field="risk_gradient_bucket", buckets=RISK_BUCKETS)
    protection_bucket_metrics = _bucket_metrics(rows, field="protection_bucket", buckets=PROTECTION_BUCKETS)
    combined_bucket_metrics = _bucket_metrics(rows, field="combined_bucket", buckets=COMBINED_BUCKETS)
    model_a = _model_summary(
        rows,
        model_id="model_a_risk_gradient_bucket",
        bucket_field="risk_gradient_bucket",
        high_bucket="high_risk",
        bucket_metrics=risk_bucket_metrics,
    )
    model_b = _model_summary(
        rows,
        model_id="model_b_protection_score_bucket",
        bucket_field="protection_bucket",
        high_bucket="high",
        bucket_metrics=protection_bucket_metrics,
    )
    model_c = _model_summary(
        rows,
        model_id="model_c_risk_gradient_plus_protection_score",
        bucket_field="combined_bucket",
        high_bucket="both_high",
        bucket_metrics=combined_bucket_metrics,
    )
    phase_rows = _phase_analysis(rows)
    consistency = {
        "model_a_risk_gradient": _phase_consistency(phase_rows, "model_a_risk_gradient"),
        "model_b_protection_score": _phase_consistency(phase_rows, "model_b_protection_score"),
        "model_c_combined": _phase_consistency(phase_rows, "model_c_combined"),
    }
    threshold = _threshold_audit(robustness_source)
    time_safety = _time_safety(rows, context_source)
    review_items = _review_items(model_b, consistency["model_b_protection_score"], threshold, time_safety)
    summary = {
        "joined_sample_count": len(rows),
        "overall": _overall_metrics(rows),
        "risk_gradient_distribution": _distribution(row.get("risk_gradient_bucket") for row in rows),
        "protection_bucket_distribution": _distribution(row.get("protection_bucket") for row in rows),
        "combined_bucket_distribution": _distribution(row.get("combined_bucket") for row in rows),
        "model_a_high_risk_lift": model_a["high_group_high_risk_lift"],
        "model_b_protection_high_risk_lift": model_b["high_group_high_risk_lift"],
        "model_c_both_high_risk_lift": model_c["high_group_high_risk_lift"],
        "protection_phase_consistency": consistency["model_b_protection_score"]["phase_consistency"],
        "ready_for_mapper_change": False,
        "ready_for_exposure_change": False,
        "conclusion": _conclusion(model_b, consistency["model_b_protection_score"]),
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": (
            "V6.4 compares fixed risk-gradient buckets with fixed protection-score buckets. "
            "It validates risk explanation only and does not authorize exposure or mapper changes."
        ),
    }
    return {
        "metadata": {
            "engine": "V6.4 Protection Score Robustness & Conditional Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (context_source.get("metadata") or {}).get("as_of"),
            "source_context_score_engine": (context_source.get("metadata") or {}).get("engine"),
            "source_risk_robustness_engine": (robustness_source.get("metadata") or {}).get("engine"),
            "source_exposure_engine": (exposure_source.get("metadata") or {}).get("engine"),
            "purpose": "Validate fixed V6.3 protection score against fixed V5 risk gradient without changing exposure policy.",
        },
        "summary": summary,
        "model_comparison": {
            "model_a_risk_gradient_bucket": model_a,
            "model_b_protection_score_bucket": model_b,
            "model_c_risk_gradient_plus_protection_score": model_c,
            "comparison_summary": _comparison_summary(model_a, model_b, model_c),
        },
        "bucket_metrics": {
            "risk_gradient_bucket": risk_bucket_metrics,
            "protection_score_bucket": protection_bucket_metrics,
            "combined_context_bucket": combined_bucket_metrics,
        },
        "phase_analysis": phase_rows,
        "phase_consistency": consistency,
        "threshold_audit": threshold,
        "time_safety": time_safety,
        "rows": rows,
        "data_quality": {
            "uses_fixed_v6_3_protection_score": True,
            "uses_fixed_v5_10_risk_gradient": True,
            "uses_fixed_v5_11_thresholds": True,
            "future_labels_used_for_validation_only": True,
            "no_parameter_optimization": True,
            "phase_conditions_are_predefined": True,
        },
        "constraints": {
            "audit_only": True,
            "does_not_modify_protection_weight": True,
            "does_not_modify_bucket_threshold": True,
            "does_not_modify_mapper": True,
            "does_not_modify_exposure_level": True,
            "does_not_generate_position": True,
            "no_percentage_exposure": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_return_optimization": True,
            "no_parameter_optimization": True,
        },
    }


def write_protection_score_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
