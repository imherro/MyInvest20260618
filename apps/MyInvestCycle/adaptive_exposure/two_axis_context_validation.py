from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "two_axis_context_validation.json"

TWO_AXIS_LABELS = (
    "PARTICIPATE",
    "PROTECT_BUT_PARTICIPATE",
    "WAIT",
    "AVOID",
    "UNKNOWN",
)
EXPOSURE_LEVELS = ("DEFENSIVE", "LOW", "BALANCED", "HIGH", "OFFENSIVE", "UNKNOWN")
DECISION_MODES = (
    "FULL_PARTICIPATION",
    "SELECTIVE_PARTICIPATION",
    "PROTECTED_PARTICIPATION",
    "DEFENSIVE",
    "WAIT",
    "UNKNOWN",
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


def _market_phase(row: Mapping[str, object]) -> str:
    return str(_context(row).get("market_phase") or row.get("market_phase") or "UNKNOWN")


def _two_axis_label(row: Mapping[str, object]) -> str:
    participation = str(row.get("participation_bucket") or "unknown")
    protection = str(row.get("protection_bucket") or "unknown")
    if participation == "unknown" or protection == "unknown":
        return "UNKNOWN"
    high_participation = participation == "high"
    high_protection = protection == "high"
    if high_participation and high_protection:
        return "PROTECT_BUT_PARTICIPATE"
    if high_participation:
        return "PARTICIPATE"
    if high_protection:
        return "AVOID"
    return "WAIT"


def _joined_rows(
    score_rows: Sequence[Mapping[str, object]],
    decision_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    decision_by_date = {str(row.get("date") or ""): row for row in decision_rows}
    rows: list[dict[str, object]] = []
    for score_row in score_rows:
        date = _date_text(score_row.get("date"))
        if not date:
            continue
        decision_row = decision_by_date.get(date, {})
        decision_mapping = decision_row if isinstance(decision_row, Mapping) else {}
        row = {
            "date": date,
            "two_axis_label": _two_axis_label(score_row),
            "participation_score": score_row.get("participation_score"),
            "protection_score": score_row.get("protection_score"),
            "participation_bucket": score_row.get("participation_bucket"),
            "protection_bucket": score_row.get("protection_bucket"),
            "v5_1_exposure_level": score_row.get("v5_1_exposure_level") or "UNKNOWN",
            "v6_2_decision_mode": decision_mapping.get("decision_mode") or "UNKNOWN",
            "market_phase": _market_phase(score_row),
            "opportunity_state": _context(score_row).get("opportunity_state"),
            "risk_state": _context(score_row).get("risk_state"),
            "future_environment": score_row.get("future_environment"),
            "future_flags": score_row.get("future_flags") or {},
            "contradictions": decision_mapping.get("contradictions") if isinstance(decision_mapping.get("contradictions"), list) else [],
            "source_trace": score_row.get("source_trace") or {},
            "data_quality": score_row.get("gradient_data_quality") or {},
            "research_label_only": True,
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
    opportunity_events = sum(1 for row in rows if _flag(row, "strong_opportunity_event"))
    drawdown_events = sum(1 for row in rows if _flag(row, "future_drawdown_gt_15"))
    contradictions = sum(1 for row in rows if _has_contradiction(row))
    return {
        "sample_count": len(rows),
        "sample_share": _share(len(rows), total_rows),
        "future_high_risk_count": high_risk_events,
        "future_high_risk_rate": _share(high_risk_events, len(rows)),
        "future_opportunity_count": opportunity_events,
        "future_opportunity_rate": _share(opportunity_events, len(rows)),
        "drawdown_event_count": drawdown_events,
        "drawdown_event_rate": _share(drawdown_events, len(rows)),
        "contradiction_count": contradictions,
        "contradiction_rate": _share(contradictions, len(rows)),
        "participation_score": _score_stats(rows, "participation_score"),
        "protection_score": _score_stats(rows, "protection_score"),
        "future_environment_distribution": _distribution(row.get("future_environment") for row in rows),
        "market_phase_distribution": _distribution(row.get("market_phase") for row in rows),
        "sample_rows": [
            {
                "date": row.get("date"),
                "two_axis_label": row.get("two_axis_label"),
                "v5_1_exposure_level": row.get("v5_1_exposure_level"),
                "v6_2_decision_mode": row.get("v6_2_decision_mode"),
                "future_environment": row.get("future_environment"),
                "future_high_risk_event": _flag(row, "high_risk_event"),
                "strong_opportunity_event": _flag(row, "strong_opportunity_event"),
                "drawdown_event": _flag(row, "future_drawdown_gt_15"),
                "contradiction": _has_contradiction(row),
            }
            for row in rows[:8]
        ],
    }


def _dimension_metrics(
    rows: Sequence[Mapping[str, object]],
    *,
    field: str,
    labels: Sequence[str],
) -> dict[str, dict[str, object]]:
    return {
        label: _metrics([row for row in rows if str(row.get(field) or "UNKNOWN") == label], len(rows))
        for label in labels
    }


def _spread(metrics: Mapping[str, Mapping[str, object]], key: str) -> dict[str, object]:
    available = [
        (label, float(item.get(key) or 0.0), int(item.get("sample_count") or 0))
        for label, item in metrics.items()
        if int(item.get("sample_count") or 0) > 0
    ]
    if not available:
        return {"spread": 0.0, "max_label": None, "min_label": None, "max_rate": None, "min_rate": None}
    max_item = max(available, key=lambda item: item[1])
    min_item = min(available, key=lambda item: item[1])
    return {
        "spread": round(max_item[1] - min_item[1], 6),
        "max_label": max_item[0],
        "min_label": min_item[0],
        "max_rate": max_item[1],
        "min_rate": min_item[1],
    }


def _dimension_summary(metrics: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    return {
        "risk_spread": _spread(metrics, "future_high_risk_rate"),
        "opportunity_spread": _spread(metrics, "future_opportunity_rate"),
        "drawdown_spread": _spread(metrics, "drawdown_event_rate"),
        "contradiction_spread": _spread(metrics, "contradiction_rate"),
    }


def _two_axis_review(rows: Sequence[Mapping[str, object]], two_axis_metrics: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    overall = _metrics(rows, len(rows))
    participate = two_axis_metrics.get("PARTICIPATE", {})
    protect = two_axis_metrics.get("PROTECT_BUT_PARTICIPATE", {})
    avoid = two_axis_metrics.get("AVOID", {})
    wait = two_axis_metrics.get("WAIT", {})
    return {
        "overall_future_high_risk_rate": overall["future_high_risk_rate"],
        "overall_future_opportunity_rate": overall["future_opportunity_rate"],
        "participate_opportunity_lift": round(float(participate.get("future_opportunity_rate") or 0.0) - float(overall["future_opportunity_rate"] or 0.0), 6),
        "avoid_risk_lift": round(float(avoid.get("future_high_risk_rate") or 0.0) - float(overall["future_high_risk_rate"] or 0.0), 6),
        "protect_but_participate_risk_lift": round(float(protect.get("future_high_risk_rate") or 0.0) - float(overall["future_high_risk_rate"] or 0.0), 6),
        "wait_opportunity_lift": round(float(wait.get("future_opportunity_rate") or 0.0) - float(overall["future_opportunity_rate"] or 0.0), 6),
        "axis_definition": {
            "high_participation": "participation_bucket == high from V6.3 fixed score_bucket",
            "high_protection": "protection_bucket == high from V6.3 fixed score_bucket",
            "non_high_bucket_treated_as_not_high": True,
        },
    }


def _comparison(
    two_axis_summary: Mapping[str, object],
    exposure_summary: Mapping[str, object],
    decision_summary: Mapping[str, object],
) -> dict[str, object]:
    two_risk = float((two_axis_summary.get("risk_spread") or {}).get("spread") or 0.0)
    two_opp = float((two_axis_summary.get("opportunity_spread") or {}).get("spread") or 0.0)
    exposure_risk = float((exposure_summary.get("risk_spread") or {}).get("spread") or 0.0)
    exposure_opp = float((exposure_summary.get("opportunity_spread") or {}).get("spread") or 0.0)
    decision_risk = float((decision_summary.get("risk_spread") or {}).get("spread") or 0.0)
    decision_opp = float((decision_summary.get("opportunity_spread") or {}).get("spread") or 0.0)
    return {
        "two_axis_minus_exposure_risk_spread": round(two_risk - exposure_risk, 6),
        "two_axis_minus_decision_risk_spread": round(two_risk - decision_risk, 6),
        "two_axis_minus_exposure_opportunity_spread": round(two_opp - exposure_opp, 6),
        "two_axis_minus_decision_opportunity_spread": round(two_opp - decision_opp, 6),
        "two_axis_risk_spread_rank": "leading" if two_risk >= max(exposure_risk, decision_risk) else "not_leading",
        "two_axis_opportunity_spread_rank": "leading" if two_opp >= max(exposure_opp, decision_opp) else "not_leading",
    }


def _time_safety(rows: Sequence[Mapping[str, object]], score_source: Mapping[str, object]) -> dict[str, object]:
    violations = [
        {"date": row.get("date"), **violation}
        for row in rows
        for violation in ((row.get("data_quality") or {}).get("time_safety_violations") or [])
    ]
    source_time_safety = score_source.get("time_safety") if isinstance(score_source.get("time_safety"), Mapping) else {}
    return {
        "feature_release_or_source_lte_signal_date": not violations and bool(source_time_safety.get("feature_release_or_source_lte_signal_date", True)),
        "violation_count": len(violations) + int(source_time_safety.get("violation_count") or 0),
        "violation_examples": violations[:10],
        "future_labels_used_for_validation_only": True,
        "participation_score_is_precomputed_v6_3": True,
        "protection_score_is_precomputed_v6_3": True,
    }


def _review_items(
    two_axis_review: Mapping[str, object],
    comparison: Mapping[str, object],
    time_safety: Mapping[str, object],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append({"type": "time_safety_violation", "severity": "high", "evidence": {"violation_count": time_safety.get("violation_count")}})
    if float(two_axis_review.get("participate_opportunity_lift") or 0.0) < 0.05:
        items.append({"type": "participation_axis_opportunity_lift_weak", "severity": "high", "evidence": {"lift": two_axis_review.get("participate_opportunity_lift")}})
    if float(two_axis_review.get("avoid_risk_lift") or 0.0) < 0.05 and float(two_axis_review.get("protect_but_participate_risk_lift") or 0.0) < 0.05:
        items.append(
            {
                "type": "protection_axis_risk_lift_weak",
                "severity": "medium",
                "evidence": {
                    "avoid_risk_lift": two_axis_review.get("avoid_risk_lift"),
                    "protect_but_participate_risk_lift": two_axis_review.get("protect_but_participate_risk_lift"),
                },
            }
        )
    if comparison.get("two_axis_risk_spread_rank") != "leading":
        items.append(
            {
                "type": "two_axis_risk_spread_not_better_than_existing_labels",
                "severity": "medium",
                "evidence": {
                    "minus_exposure": comparison.get("two_axis_minus_exposure_risk_spread"),
                    "minus_decision": comparison.get("two_axis_minus_decision_risk_spread"),
                },
            }
        )
    items.append(
        {
            "type": "two_axis_context_research_only_do_not_modify_exposure",
            "severity": "high",
            "evidence": {"reason": "V6.5 audits fixed V6.3 scores only; no mapper, exposure, ETF, weight, or trade change."},
        }
    )
    return items


def _conclusion(two_axis_review: Mapping[str, object], comparison: Mapping[str, object]) -> str:
    opportunity_lift = float(two_axis_review.get("participate_opportunity_lift") or 0.0)
    protection_lift = max(
        float(two_axis_review.get("avoid_risk_lift") or 0.0),
        float(two_axis_review.get("protect_but_participate_risk_lift") or 0.0),
    )
    if protection_lift >= 0.05 and opportunity_lift < 0.05:
        return "risk_axis_visible_opportunity_axis_weak"
    if protection_lift >= 0.05 and opportunity_lift >= 0.05 and comparison.get("two_axis_risk_spread_rank") == "leading":
        return "two_axis_research_value_visible_not_policy_ready"
    return "two_axis_context_not_validated"


def build_two_axis_context_validation(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    score_source = _read_json(root / "exposure_context_score_audit.json")
    protection_source = _read_json(root / "protection_score_validation.json")
    decision_source = _read_json(root / "exposure_decision_audit.json")
    if not isinstance(score_source, Mapping) or not isinstance(score_source.get("rows"), list):
        raise RuntimeError("exposure_context_score_audit.json is missing or incomplete.")
    if not isinstance(decision_source, Mapping) or not isinstance(decision_source.get("rows"), list):
        raise RuntimeError("exposure_decision_audit.json is missing or incomplete.")
    if not isinstance(protection_source, Mapping):
        protection_source = {}

    rows = _joined_rows(
        [row for row in score_source.get("rows") or [] if isinstance(row, Mapping)],
        [row for row in decision_source.get("rows") or [] if isinstance(row, Mapping)],
    )
    two_axis_metrics = _dimension_metrics(rows, field="two_axis_label", labels=TWO_AXIS_LABELS)
    exposure_metrics = _dimension_metrics(rows, field="v5_1_exposure_level", labels=EXPOSURE_LEVELS)
    decision_metrics = _dimension_metrics(rows, field="v6_2_decision_mode", labels=DECISION_MODES)
    two_axis_dimension = _dimension_summary(two_axis_metrics)
    exposure_dimension = _dimension_summary(exposure_metrics)
    decision_dimension = _dimension_summary(decision_metrics)
    axis_review = _two_axis_review(rows, two_axis_metrics)
    dimension_comparison = _comparison(two_axis_dimension, exposure_dimension, decision_dimension)
    time_safety = _time_safety(rows, score_source)
    review_items = _review_items(axis_review, dimension_comparison, time_safety)
    summary = {
        "joined_sample_count": len(rows),
        "two_axis_distribution": _distribution(row.get("two_axis_label") for row in rows),
        "two_axis_risk_spread": two_axis_dimension["risk_spread"]["spread"],
        "two_axis_opportunity_spread": two_axis_dimension["opportunity_spread"]["spread"],
        "exposure_level_risk_spread": exposure_dimension["risk_spread"]["spread"],
        "decision_mode_risk_spread": decision_dimension["risk_spread"]["spread"],
        "participate_opportunity_lift": axis_review["participate_opportunity_lift"],
        "avoid_risk_lift": axis_review["avoid_risk_lift"],
        "protect_but_participate_risk_lift": axis_review["protect_but_participate_risk_lift"],
        "ready_for_mapper_change": False,
        "ready_for_exposure_change": False,
        "conclusion": _conclusion(axis_review, dimension_comparison),
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": "The two-axis map is a research-only environment map built from fixed V6.3 participation/protection buckets.",
    }
    return {
        "metadata": {
            "engine": "V6.5 Adaptive Context Two-Axis Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (score_source.get("metadata") or {}).get("as_of"),
            "source_context_score_engine": (score_source.get("metadata") or {}).get("engine"),
            "source_protection_validation_engine": (protection_source.get("metadata") or {}).get("engine"),
            "source_decision_engine": (decision_source.get("metadata") or {}).get("engine"),
            "purpose": "Validate fixed participation/protection score axes as a research-only environment map.",
        },
        "summary": summary,
        "two_axis_review": axis_review,
        "dimension_comparison": dimension_comparison,
        "dimension_summaries": {
            "two_axis": two_axis_dimension,
            "v5_1_exposure_level": exposure_dimension,
            "v6_2_decision_mode": decision_dimension,
        },
        "dimension_metrics": {
            "two_axis": two_axis_metrics,
            "v5_1_exposure_level": exposure_metrics,
            "v6_2_decision_mode": decision_metrics,
        },
        "rows": rows,
        "time_safety": time_safety,
        "data_quality": {
            "uses_fixed_v6_3_participation_score": True,
            "uses_fixed_v6_3_protection_score": True,
            "uses_v6_4_for_source_context_only": True,
            "future_labels_used_for_validation_only": True,
            "no_parameter_optimization": True,
            "two_axis_thresholds_reuse_v6_3_buckets": True,
        },
        "constraints": {
            "audit_only": True,
            "research_label_only": True,
            "does_not_modify_score_weight": True,
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


def write_two_axis_context_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
