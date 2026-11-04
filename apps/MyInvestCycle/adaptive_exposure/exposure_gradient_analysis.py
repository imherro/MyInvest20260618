from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean, median
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "exposure_gradient_analysis.json"

RISK_BUCKETS = ("high_risk", "medium_risk", "low_risk", "unknown")
OPPORTUNITY_BUCKETS = ("high_opportunity", "medium_opportunity", "low_opportunity", "unknown")


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
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 4)


def _context(row: Mapping[str, object]) -> Mapping[str, object]:
    context = row.get("analysis_context")
    return context if isinstance(context, Mapping) else {}


def _number(row: Mapping[str, object], field: str) -> float | None:
    return _to_float(_context(row).get(field))


def _inverse_score(value: float | None) -> float | None:
    return None if value is None else _clamp(100.0 - value)


def _m1_m2_weakness(value: float | None) -> float | None:
    if value is None:
        return None
    if value >= 2:
        return 0.0
    if value <= -8:
        return 100.0
    return _clamp((2 - value) / 10 * 100)


def _binary_score(enabled: bool, *, high: float = 80.0, low: float = 20.0) -> float:
    return high if enabled else low


def _weighted_score(components: Sequence[tuple[str, float | None, float]]) -> tuple[float | None, list[dict[str, object]]]:
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


def _risk_gradient(row: Mapping[str, object]) -> tuple[float | None, list[dict[str, object]]]:
    context = _context(row)
    risk_crowded = context.get("risk_state") == "CROWDED"
    components = (
        ("breadth_weakness", _inverse_score(_number(row, "breadth_score")), 0.18),
        ("liquidity_weakness", _inverse_score(_number(row, "liquidity_score")), 0.18),
        ("trend_weakness", _inverse_score(_number(row, "trend_score")), 0.12),
        ("price_extension", _number(row, "price_extension_proxy"), 0.16),
        ("crowding_state", _binary_score(risk_crowded, high=75.0, low=25.0), 0.14),
        ("credit_weakness", _inverse_score(_number(row, "credit_score")), 0.10),
        ("m1_m2_weakness", _m1_m2_weakness(_number(row, "M1_M2_spread")), 0.12),
    )
    return _weighted_score(components)


def _opportunity_gradient(row: Mapping[str, object]) -> tuple[float | None, list[dict[str, object]]]:
    context = _context(row)
    structural_rotation = context.get("opportunity_state") == "STRUCTURAL_ROTATION"
    components = (
        ("macro_support", _number(row, "macro_score"), 0.18),
        ("economy_support", _number(row, "economy_score"), 0.12),
        ("credit_support", _number(row, "credit_score"), 0.12),
        ("trend_support", _number(row, "trend_score"), 0.16),
        ("liquidity_support", _number(row, "liquidity_score"), 0.12),
        ("industry_breadth", _number(row, "industry_breadth"), 0.10),
        ("theme_persistence", _number(row, "theme_persistence"), 0.10),
        ("structural_rotation", _binary_score(structural_rotation, high=80.0, low=25.0), 0.10),
    )
    return _weighted_score(components)


def _risk_bucket(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 65:
        return "high_risk"
    if score >= 45:
        return "medium_risk"
    return "low_risk"


def _opportunity_bucket(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 65:
        return "high_opportunity"
    if score >= 45:
        return "medium_opportunity"
    return "low_opportunity"


def _outcome_label(row: Mapping[str, object]) -> str:
    outcome = str(row.get("outcome") or "")
    if outcome in {"failure", "missed_opportunity", "neutral"}:
        return outcome
    future_label = row.get("future_label") if isinstance(row.get("future_label"), Mapping) else {}
    if future_label.get("failure"):
        return "failure"
    if future_label.get("missed_opportunity"):
        return "missed_opportunity"
    return "neutral"


def _row_time_safety(row: Mapping[str, object]) -> tuple[bool, list[dict[str, object]]]:
    signal_date = str(row.get("date") or "")
    trace_map = row.get("source_trace") if isinstance(row.get("source_trace"), Mapping) else {}
    violations = []
    for field, trace in trace_map.items():
        if not isinstance(trace, Mapping) or trace.get("available") is not True:
            continue
        for key in ("source_date", "release_date", "effective_date"):
            value = trace.get(key)
            if value is not None and str(value) > signal_date:
                violations.append({"field": field, key: value, "signal_date": signal_date})
    return not violations, violations


def _gradient_row(row: Mapping[str, object]) -> dict[str, object] | None:
    date_text = _date_text(row.get("date"))
    if not date_text:
        return None
    risk_score, risk_components = _risk_gradient(row)
    opportunity_score, opportunity_components = _opportunity_gradient(row)
    time_safe, violations = _row_time_safety(row)
    return {
        "date": date_text,
        "context_state": row.get("context_state"),
        "source_candidate": row.get("source_candidate"),
        "outcome": _outcome_label(row),
        "risk_gradient_score": risk_score,
        "opportunity_gradient_score": opportunity_score,
        "risk_gradient_bucket": _risk_bucket(risk_score),
        "opportunity_gradient_bucket": _opportunity_bucket(opportunity_score),
        "risk_components": risk_components,
        "opportunity_components": opportunity_components,
        "analysis_context": row.get("analysis_context"),
        "future_label": row.get("future_label"),
        "source_trace": row.get("source_trace"),
        "data_quality": {
            "time_safe": time_safe,
            "time_safety_violations": violations,
            "risk_component_count": len(risk_components),
            "opportunity_component_count": len(opportunity_components),
            "future_label_not_used_for_gradient": True,
        },
    }


def _rate(rows: Sequence[Mapping[str, object]], outcome: str) -> float:
    return _share(sum(1 for row in rows if row.get("outcome") == outcome), len(rows))


def _confidence(rows: Sequence[Mapping[str, object]], component_key: str) -> str:
    if not rows:
        return "low"
    component_counts = [
        int((row.get("data_quality") or {}).get(component_key) or 0)
        for row in rows
        if isinstance(row.get("data_quality"), Mapping)
    ]
    avg_components = mean(component_counts) if component_counts else 0.0
    years = {str(row.get("date"))[:4] for row in rows if _date_text(row.get("date"))}
    if len(rows) >= 20 and avg_components >= 5 and len(years) >= 4:
        return "medium"
    if len(rows) >= 8 and avg_components >= 4 and len(years) >= 2:
        return "low_medium"
    return "low"


def _bucket_analysis(
    rows: Sequence[Mapping[str, object]],
    *,
    bucket_key: str,
    buckets: Sequence[str],
    component_key: str,
) -> dict[str, dict[str, object]]:
    payload = {}
    for bucket in buckets:
        group_rows = [row for row in rows if row.get(bucket_key) == bucket]
        payload[bucket] = {
            "sample_count": len(group_rows),
            "share_of_balanced": _share(len(group_rows), len(rows)),
            "future_failure_rate": _rate(group_rows, "failure"),
            "future_opportunity_rate": _rate(group_rows, "missed_opportunity"),
            "outcome_distribution": _distribution(row.get("outcome") for row in group_rows),
            "context_state_distribution": _distribution(row.get("context_state") for row in group_rows),
            "confidence": _confidence(group_rows, component_key),
            "sample_rows": [
                {
                    "date": row.get("date"),
                    "outcome": row.get("outcome"),
                    "context_state": row.get("context_state"),
                    "risk_gradient_score": row.get("risk_gradient_score"),
                    "opportunity_gradient_score": row.get("opportunity_gradient_score"),
                }
                for row in group_rows[:5]
            ],
        }
    return payload


def _score_stats(rows: Sequence[Mapping[str, object]], field: str) -> dict[str, object]:
    values = [_to_float(row.get(field)) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return {"available_count": 0, "coverage_rate": 0.0, "avg": None, "median": None}
    return {
        "available_count": len(values),
        "coverage_rate": _share(len(values), len(rows)),
        "avg": round(mean(values), 4),
        "median": round(median(values), 4),
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
        "no_future_fill": True,
    }


def _separation_review(rows: Sequence[Mapping[str, object]], risk_buckets: Mapping[str, Mapping[str, object]], opportunity_buckets: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    overall_risk = _rate(rows, "failure")
    overall_opportunity = _rate(rows, "missed_opportunity")
    high_risk = risk_buckets.get("high_risk", {})
    high_opportunity = opportunity_buckets.get("high_opportunity", {})
    risk_lift = round(float(high_risk.get("future_failure_rate") or 0.0) - overall_risk, 6)
    opportunity_lift = round(float(high_opportunity.get("future_opportunity_rate") or 0.0) - overall_opportunity, 6)
    return {
        "overall_future_risk_rate": overall_risk,
        "overall_future_opportunity_rate": overall_opportunity,
        "high_risk_bucket_failure_lift": risk_lift,
        "high_opportunity_bucket_opportunity_lift": opportunity_lift,
        "risk_gradient_separation": "visible" if risk_lift >= 0.05 and int(high_risk.get("sample_count") or 0) >= 8 else "weak",
        "opportunity_gradient_separation": "visible" if opportunity_lift >= 0.05 and int(high_opportunity.get("sample_count") or 0) >= 8 else "weak",
    }


def _review_items(separation: Mapping[str, object], time_safety: Mapping[str, object]) -> list[dict[str, object]]:
    items = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append({"type": "time_safety_violation", "severity": "high", "evidence": {"violation_count": time_safety.get("violation_count")}})
    if separation.get("risk_gradient_separation") == "weak":
        items.append({"type": "risk_gradient_edge_weak", "severity": "medium", "evidence": {"risk_lift": separation.get("high_risk_bucket_failure_lift")}})
    if separation.get("opportunity_gradient_separation") == "weak":
        items.append({"type": "opportunity_gradient_edge_weak", "severity": "medium", "evidence": {"opportunity_lift": separation.get("high_opportunity_bucket_opportunity_lift")}})
    items.append(
        {
            "type": "gradient_research_only_do_not_modify_mapper",
            "severity": "high",
            "evidence": {"reason": "V5.10 is continuous-gradient research only; no exposure mapper or policy change."},
        }
    )
    return items


def build_exposure_gradient_analysis(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    source = _read_json(root / "exposure_context_state_audit.json")
    if not isinstance(source, Mapping) or not isinstance(source.get("rows"), list):
        raise RuntimeError("exposure_context_state_audit.json is missing or incomplete.")
    rows = [
        gradient_row
        for source_row in source.get("rows") or []
        if isinstance(source_row, Mapping)
        for gradient_row in [_gradient_row(source_row)]
        if gradient_row is not None
    ]
    risk_bucket_analysis = _bucket_analysis(
        rows,
        bucket_key="risk_gradient_bucket",
        buckets=RISK_BUCKETS,
        component_key="risk_component_count",
    )
    opportunity_bucket_analysis = _bucket_analysis(
        rows,
        bucket_key="opportunity_gradient_bucket",
        buckets=OPPORTUNITY_BUCKETS,
        component_key="opportunity_component_count",
    )
    time_safety = _time_safety(rows)
    separation = _separation_review(rows, risk_bucket_analysis, opportunity_bucket_analysis)
    review_items = _review_items(separation, time_safety)
    summary = {
        "balanced_usable_rows": len(rows),
        "risk_gradient_distribution": _distribution(row.get("risk_gradient_bucket") for row in rows),
        "opportunity_gradient_distribution": _distribution(row.get("opportunity_gradient_bucket") for row in rows),
        "score_coverage": {
            "risk_gradient_score": _score_stats(rows, "risk_gradient_score"),
            "opportunity_gradient_score": _score_stats(rows, "opportunity_gradient_score"),
        },
        "separation_review": separation,
        "time_safety": time_safety,
        "ready_for_mapper_change": False,
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": (
            "Continuous gradients provide another research lens for BALANCED, but they remain research-only "
            "until high-risk and high-opportunity buckets show stable lift."
        ),
    }
    return {
        "metadata": {
            "engine": "V5.10 Exposure Context Risk Gradient Analysis",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (source.get("metadata") or {}).get("as_of"),
            "source_engine": (source.get("metadata") or {}).get("engine"),
            "purpose": "Analyze continuous risk and opportunity gradients inside BALANCED without changing exposure rules.",
        },
        "summary": summary,
        "risk_bucket_analysis": risk_bucket_analysis,
        "opportunity_bucket_analysis": opportunity_bucket_analysis,
        "rows": rows,
        "data_quality": {
            "uses_v5_9_context_state_rows": True,
            "future_labels_used_for_validation_only": True,
            "future_label_not_used_for_gradient": True,
            "feature_release_or_source_lte_signal_date": time_safety["feature_release_or_source_lte_signal_date"],
            "missing_values_are_skipped_not_zero": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "audit_only": True,
            "continuous_gradient_research_only": True,
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
            "no_return_optimization": True,
        },
    }


def write_exposure_gradient_analysis(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
