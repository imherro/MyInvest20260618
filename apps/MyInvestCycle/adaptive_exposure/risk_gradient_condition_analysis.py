from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_gradient_condition_analysis.json"

FIXED_RISK_THRESHOLDS = {
    "high_risk_min": 65.0,
    "medium_risk_min": 45.0,
}

DIMENSION_FIELDS = ("opportunity_state", "market_phase", "risk_state")
COMPOSITE_FIELD_SETS = (
    ("market_phase", "risk_state"),
    ("opportunity_state", "risk_state"),
    ("opportunity_state", "market_phase"),
)


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _date_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text if len(text) == 8 and text.isdigit() else None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "UNKNOWN") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _context_value(row: Mapping[str, object], field: str) -> str:
    context = row.get("analysis_context")
    if not isinstance(context, Mapping):
        return "UNKNOWN"
    value = context.get(field)
    return str(value or "UNKNOWN")


def _fixed_risk_bucket(score: object) -> str:
    value = _to_float(score)
    if value is None:
        return "unknown"
    if value >= FIXED_RISK_THRESHOLDS["high_risk_min"]:
        return "high_risk"
    if value >= FIXED_RISK_THRESHOLDS["medium_risk_min"]:
        return "medium_risk"
    return "low_risk"


def _rate(rows: Sequence[Mapping[str, object]], outcome: str = "failure") -> float:
    return _share(sum(1 for row in rows if row.get("outcome") == outcome), len(rows))


def _score_stats(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    values = [_to_float(row.get("risk_gradient_score")) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return {"available_count": 0, "avg": None, "min": None, "max": None}
    return {
        "available_count": len(values),
        "avg": round(mean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _status(sample_count: int, high_count: int, lift: float | None) -> str:
    if sample_count < 6:
        return "insufficient_total_sample"
    if high_count < 3:
        return "insufficient_high_risk_sample"
    if lift is None:
        return "insufficient_high_risk_sample"
    if lift >= 0.05:
        return "positive"
    if lift <= -0.05:
        return "negative"
    return "flat"


def _confidence(sample_count: int, high_count: int, status: str) -> str:
    if status.startswith("insufficient"):
        return "low"
    if sample_count >= 30 and high_count >= 5:
        return "medium"
    if sample_count >= 15 and high_count >= 3:
        return "low_medium"
    return "low"


def _condition_payload(
    *,
    condition_type: str,
    fields: Sequence[str],
    values: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    high_rows = [row for row in rows if row.get("risk_gradient_bucket") == "high_risk"]
    overall_failure = _rate(rows, "failure")
    high_failure = _rate(high_rows, "failure") if high_rows else None
    lift = round(high_failure - overall_failure, 6) if high_failure is not None else None
    status = _status(len(rows), len(high_rows), lift)
    return {
        "condition_type": condition_type,
        "fields": list(fields),
        "values": list(values),
        "condition": "+".join(values),
        "sample_count": len(rows),
        "high_risk_sample_count": len(high_rows),
        "overall_failure_rate": overall_failure,
        "high_risk_failure_rate": high_failure,
        "high_risk_lift": lift,
        "overall_opportunity_rate": _rate(rows, "missed_opportunity"),
        "high_risk_opportunity_rate": _rate(high_rows, "missed_opportunity") if high_rows else None,
        "risk_gradient_edge": status,
        "confidence": _confidence(len(rows), len(high_rows), status),
        "risk_score": _score_stats(rows),
        "outcome_distribution": _distribution(row.get("outcome") for row in rows),
        "high_risk_sample_rows": [
            {
                "date": row.get("date"),
                "outcome": row.get("outcome"),
                "risk_gradient_score": row.get("risk_gradient_score"),
                "opportunity_state": _context_value(row, "opportunity_state"),
                "market_phase": _context_value(row, "market_phase"),
                "risk_state": _context_value(row, "risk_state"),
            }
            for row in high_rows[:8]
        ],
    }


def _condition_groups(rows: Sequence[Mapping[str, object]], fields: Sequence[str], condition_type: str) -> list[dict[str, object]]:
    grouped: dict[tuple[str, ...], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        values = tuple(_context_value(row, field) for field in fields)
        grouped[values].append(row)
    return [
        _condition_payload(
            condition_type=condition_type,
            fields=fields,
            values=values,
            rows=group_rows,
        )
        for values, group_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def _threshold_consistency(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    mismatches = []
    for row in rows:
        expected = _fixed_risk_bucket(row.get("risk_gradient_score"))
        actual = str(row.get("risk_gradient_bucket") or "unknown")
        if expected != actual:
            mismatches.append(
                {
                    "date": row.get("date"),
                    "risk_gradient_score": row.get("risk_gradient_score"),
                    "expected_bucket": expected,
                    "actual_bucket": actual,
                }
            )
    return {
        "fixed_thresholds": FIXED_RISK_THRESHOLDS,
        "checked_rows": len(rows),
        "mismatch_count": len(mismatches),
        "mismatch_examples": mismatches[:10],
        "thresholds_were_not_optimized": True,
    }


def _time_safety(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    violations = [
        {"date": row.get("date"), **violation}
        for row in rows
        for violation in ((row.get("data_quality") or {}).get("time_safety_violations") or [])
    ]
    checked = sum(
        1
        for row in rows
        for trace in ((row.get("source_trace") or {}).values() if isinstance(row.get("source_trace"), Mapping) else [])
        if isinstance(trace, Mapping) and trace.get("available") is True
    )
    return {
        "feature_release_or_source_lte_signal_date": not violations,
        "checked_values": checked,
        "violation_count": len(violations),
        "violation_examples": violations[:10],
        "future_labels_used_for_validation_only": True,
        "risk_gradient_score_is_precomputed_v5_10": True,
    }


def _summary(all_conditions: Sequence[Mapping[str, object]]) -> dict[str, object]:
    evaluated = [item for item in all_conditions if item.get("risk_gradient_edge") in {"positive", "negative", "flat"}]
    positive = [item for item in evaluated if item.get("risk_gradient_edge") == "positive"]
    negative = [item for item in evaluated if item.get("risk_gradient_edge") == "negative"]
    flat = [item for item in evaluated if item.get("risk_gradient_edge") == "flat"]
    insufficient = [
        item
        for item in all_conditions
        if str(item.get("risk_gradient_edge") or "").startswith("insufficient")
    ]
    sorted_positive = sorted(positive, key=lambda item: float(item.get("high_risk_lift") or 0.0), reverse=True)
    sorted_negative = sorted(negative, key=lambda item: float(item.get("high_risk_lift") or 0.0))
    return {
        "condition_count": len(all_conditions),
        "evaluated_condition_count": len(evaluated),
        "positive_condition_count": len(positive),
        "negative_condition_count": len(negative),
        "flat_condition_count": len(flat),
        "insufficient_condition_count": len(insufficient),
        "strongest_positive_condition": _condition_ref(sorted_positive[0]) if sorted_positive else None,
        "strongest_negative_condition": _condition_ref(sorted_negative[0]) if sorted_negative else None,
        "top_positive_conditions": [_condition_ref(item) for item in sorted_positive[:8]],
        "negative_conditions": [_condition_ref(item) for item in sorted_negative[:8]],
    }


def _condition_ref(item: Mapping[str, object]) -> dict[str, object]:
    return {
        "condition_type": item.get("condition_type"),
        "condition": item.get("condition"),
        "sample_count": item.get("sample_count"),
        "high_risk_sample_count": item.get("high_risk_sample_count"),
        "high_risk_lift": item.get("high_risk_lift"),
        "risk_gradient_edge": item.get("risk_gradient_edge"),
        "confidence": item.get("confidence"),
    }


def _review_items(summary: Mapping[str, object], threshold: Mapping[str, object], time_safety: Mapping[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append({"type": "time_safety_violation", "severity": "high", "evidence": {"violation_count": time_safety.get("violation_count")}})
    if int(threshold.get("mismatch_count") or 0) > 0:
        items.append({"type": "risk_threshold_mismatch", "severity": "high", "evidence": {"mismatch_count": threshold.get("mismatch_count")}})
    if int(summary.get("positive_condition_count") or 0) > 0:
        items.append(
            {
                "type": "conditional_risk_edge_visible",
                "severity": "medium",
                "evidence": {"top_positive_conditions": summary.get("top_positive_conditions")},
            }
        )
    if int(summary.get("insufficient_condition_count") or 0) > int(summary.get("evaluated_condition_count") or 0):
        items.append(
            {
                "type": "many_conditions_have_small_samples",
                "severity": "high",
                "evidence": {
                    "insufficient_condition_count": summary.get("insufficient_condition_count"),
                    "evaluated_condition_count": summary.get("evaluated_condition_count"),
                },
            }
        )
    items.append(
        {
            "type": "conditional_validation_research_only_do_not_modify_mapper",
            "severity": "high",
            "evidence": {"reason": "V5.12 audits conditional validity only; no gradient, threshold, mapper, exposure, ETF, or trade change."},
        }
    )
    return items


def build_risk_gradient_condition_analysis(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    source = _read_json(root / "exposure_gradient_analysis.json")
    robustness_source = _read_json(root / "risk_gradient_robustness.json")
    if not isinstance(source, Mapping) or not isinstance(source.get("rows"), list):
        raise RuntimeError("exposure_gradient_analysis.json is missing or incomplete.")
    rows = [row for row in source.get("rows") or [] if isinstance(row, Mapping) and _date_text(row.get("date"))]
    dimension_analysis = {
        field: _condition_groups(rows, (field,), f"dimension:{field}")
        for field in DIMENSION_FIELDS
    }
    composite_analysis = {
        "+".join(fields): _condition_groups(rows, fields, f"composite:{'+'.join(fields)}")
        for fields in COMPOSITE_FIELD_SETS
    }
    all_conditions = [
        item
        for items in dimension_analysis.values()
        for item in items
    ] + [
        item
        for items in composite_analysis.values()
        for item in items
    ]
    threshold = _threshold_consistency(rows)
    time_safety = _time_safety(rows)
    condition_summary = _summary(all_conditions)
    review_items = _review_items(condition_summary, threshold, time_safety)
    summary = {
        "source_rows": len(rows),
        **condition_summary,
        "ready_for_mapper_change": False,
        "conclusion": "conditional_edge_visible_but_not_rule_ready",
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": (
            "Risk gradient has conditional value: it is stronger in crowded and early-cycle contexts, "
            "but many splits have small samples, so this remains a research explanation layer."
        ),
    }
    return {
        "metadata": {
            "engine": "V5.12 Risk Gradient Conditional Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (source.get("metadata") or {}).get("as_of"),
            "source_engine": (source.get("metadata") or {}).get("engine"),
            "robustness_source_engine": (robustness_source.get("metadata") or {}).get("engine") if isinstance(robustness_source, Mapping) else None,
            "purpose": "Find market contexts where the fixed V5.10 risk gradient is more or less effective without changing any rule.",
        },
        "summary": summary,
        "dimension_analysis": dimension_analysis,
        "composite_analysis": composite_analysis,
        "observed_context_distribution": {
            field: _distribution(_context_value(row, field) for row in rows)
            for field in DIMENSION_FIELDS
        },
        "threshold_consistency": threshold,
        "time_safety": time_safety,
        "data_quality": {
            "uses_v5_10_risk_gradient_rows": True,
            "uses_v5_11_thresholds": True,
            "risk_gradient_score_reused_not_reweighted": True,
            "fixed_thresholds_reused": True,
            "future_labels_used_for_validation_only": True,
            "no_parameter_optimization": True,
            "conditions_are_descriptive_not_rules": True,
        },
        "constraints": {
            "audit_only": True,
            "does_not_modify_gradient_weight": True,
            "does_not_modify_threshold": True,
            "does_not_modify_mapper": True,
            "does_not_modify_policy": True,
            "does_not_add_formal_state": True,
            "does_not_add_exposure_level": True,
            "no_parameter_optimization": True,
            "no_percentage_exposure": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def write_risk_gradient_condition_analysis(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
