from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "context_information_attribution.json"

LAYER_DEFINITIONS = (
    {
        "layer_id": "layer_0_v5_1_exposure_level",
        "layer_name": "V5.1 Exposure Level",
        "field": "v5_1_exposure_level",
        "risk_focus_label": "DEFENSIVE",
        "source": "V5.1 exposure_simulation / V6.5 common sample",
    },
    {
        "layer_id": "layer_1_risk_gradient",
        "layer_name": "Risk Gradient",
        "field": "risk_gradient_bucket",
        "risk_focus_label": "high_risk",
        "source": "V5.10 exposure_gradient_analysis / V6.3 common sample",
    },
    {
        "layer_id": "layer_2_protection_score",
        "layer_name": "Protection Score",
        "field": "protection_bucket",
        "risk_focus_label": "high",
        "source": "V6.3 protection_score fixed bucket",
    },
    {
        "layer_id": "layer_3_two_axis_context",
        "layer_name": "Two Axis Context",
        "field": "two_axis_label",
        "risk_focus_label": "PROTECT_BUT_PARTICIPATE",
        "source": "V6.5 two_axis_context_validation",
    },
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


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "UNKNOWN") for value in values)
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


def _joined_rows(
    two_axis_rows: Sequence[Mapping[str, object]],
    score_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    score_by_date = {str(row.get("date") or ""): row for row in score_rows}
    rows: list[dict[str, object]] = []
    for row in two_axis_rows:
        date = _date_text(row.get("date"))
        if not date:
            continue
        score_row = score_by_date.get(date, {})
        score_mapping = score_row if isinstance(score_row, Mapping) else {}
        rows.append(
            {
                "date": date,
                "market_phase": row.get("market_phase") or "UNKNOWN",
                "v5_1_exposure_level": row.get("v5_1_exposure_level") or "UNKNOWN",
                "risk_gradient_bucket": score_mapping.get("risk_gradient_bucket") or "unknown",
                "protection_bucket": row.get("protection_bucket") or "unknown",
                "two_axis_label": row.get("two_axis_label") or "UNKNOWN",
                "future_environment": row.get("future_environment"),
                "future_flags": row.get("future_flags") or {},
                "contradictions": row.get("contradictions") if isinstance(row.get("contradictions"), list) else [],
                "data_quality": row.get("data_quality") or {},
            }
        )
    return rows


def _metrics(rows: Sequence[Mapping[str, object]], total_rows: int) -> dict[str, object]:
    high_risk = sum(1 for row in rows if _flag(row, "high_risk_event"))
    opportunity = sum(1 for row in rows if _flag(row, "strong_opportunity_event"))
    drawdown = sum(1 for row in rows if _flag(row, "future_drawdown_gt_15"))
    contradiction = sum(1 for row in rows if _has_contradiction(row))
    return {
        "sample_count": len(rows),
        "sample_share": _share(len(rows), total_rows),
        "future_high_risk_count": high_risk,
        "future_high_risk_rate": _share(high_risk, len(rows)),
        "future_opportunity_count": opportunity,
        "future_opportunity_rate": _share(opportunity, len(rows)),
        "drawdown_event_count": drawdown,
        "drawdown_event_rate": _share(drawdown, len(rows)),
        "contradiction_count": contradiction,
        "contradiction_rate": _share(contradiction, len(rows)),
    }


def _group_metrics(rows: Sequence[Mapping[str, object]], field: str) -> dict[str, dict[str, object]]:
    labels = sorted({str(row.get(field) or "UNKNOWN") for row in rows})
    return {
        label: _metrics([row for row in rows if str(row.get(field) or "UNKNOWN") == label], len(rows))
        for label in labels
    }


def _spread(groups: Mapping[str, Mapping[str, object]], metric_key: str) -> dict[str, object]:
    available = [
        (label, float(metrics.get(metric_key) or 0.0), int(metrics.get("sample_count") or 0))
        for label, metrics in groups.items()
        if int(metrics.get("sample_count") or 0) > 0
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


def _phase_status(total_rows: int, focus_rows: int, lift: float | None) -> str:
    if total_rows < 6:
        return "insufficient_total_sample"
    if focus_rows < 3:
        return "insufficient_focus_sample"
    if lift is None:
        return "insufficient_focus_sample"
    if lift >= 0.05:
        return "positive"
    if lift <= -0.05:
        return "negative"
    return "flat"


def _phase_consistency(
    rows: Sequence[Mapping[str, object]],
    *,
    field: str,
    risk_focus_label: str,
) -> dict[str, object]:
    periods = []
    for phase in FOCUS_PHASES:
        phase_rows = [row for row in rows if row.get("market_phase") == phase]
        focus_rows = [row for row in phase_rows if str(row.get(field) or "UNKNOWN") == risk_focus_label]
        overall_rate = _metrics(phase_rows, len(phase_rows)).get("future_high_risk_rate")
        focus_rate = _metrics(focus_rows, len(phase_rows)).get("future_high_risk_rate") if focus_rows else None
        lift = round(float(focus_rate or 0.0) - float(overall_rate or 0.0), 6) if focus_rate is not None else None
        periods.append(
            {
                "market_phase": phase,
                "sample_count": len(phase_rows),
                "focus_label": risk_focus_label,
                "focus_sample_count": len(focus_rows),
                "overall_future_high_risk_rate": overall_rate,
                "focus_future_high_risk_rate": focus_rate,
                "focus_high_risk_lift": lift,
                "status": _phase_status(len(phase_rows), len(focus_rows), lift),
            }
        )
    statuses = [period["status"] for period in periods]
    evaluated = [status for status in statuses if status in {"positive", "negative", "flat"}]
    positive = [status for status in evaluated if status == "positive"]
    negative = [status for status in evaluated if status == "negative"]
    if len(evaluated) < 2:
        consistency = "insufficient_evidence"
    elif len(negative) == 0 and _share(len(positive), len(evaluated)) >= 0.75:
        consistency = "high"
    elif len(negative) <= 1 and _share(len(positive), len(evaluated)) >= 0.5:
        consistency = "medium"
    else:
        consistency = "weak"
    return {
        "phase_consistency": consistency,
        "evaluated_phase_count": len(evaluated),
        "positive_phase_count": len(positive),
        "negative_phase_count": len(negative),
        "insufficient_phase_count": len([status for status in statuses if status.startswith("insufficient")]),
        "periods": periods,
    }


def _layer_status(risk_spread: float, opportunity_spread: float, consistency: str) -> str:
    if risk_spread < 0.05 and opportunity_spread < 0.05:
        return "no_clear_incremental_value"
    if risk_spread >= 0.10 and consistency in {"high", "medium"} and opportunity_spread < 0.05:
        return "risk_value_only"
    if risk_spread >= 0.10 and opportunity_spread >= 0.10:
        return "research_value"
    if risk_spread >= 0.05:
        return "weak_risk_value"
    if opportunity_spread >= 0.05:
        return "weak_opportunity_value"
    return "no_clear_incremental_value"


def _retention(layer_id: str, status: str) -> str:
    if layer_id == "layer_0_v5_1_exposure_level":
        return "baseline_only_do_not_use_as_validation_axis"
    if layer_id == "layer_1_risk_gradient":
        return "keep_as_primary_risk_axis" if status != "no_clear_incremental_value" else "review"
    if layer_id == "layer_2_protection_score":
        return "keep_as_risk_confirmation_layer" if status != "no_clear_incremental_value" else "review"
    if layer_id == "layer_3_two_axis_context":
        return "keep_as_research_context_map_not_policy"
    return "review"


def _layer_attribution(rows: Sequence[Mapping[str, object]], definition: Mapping[str, str], previous: Mapping[str, object] | None) -> dict[str, object]:
    field = definition["field"]
    groups = _group_metrics(rows, field)
    risk_spread = _spread(groups, "future_high_risk_rate")
    opportunity_spread = _spread(groups, "future_opportunity_rate")
    drawdown_spread = _spread(groups, "drawdown_event_rate")
    contradiction_spread = _spread(groups, "contradiction_rate")
    coverage = _share(sum(int(group.get("sample_count") or 0) for group in groups.values()), len(rows))
    top_group = max(groups.items(), key=lambda item: int(item[1].get("sample_count") or 0))[0] if groups else None
    top_share = max((float(group.get("sample_share") or 0.0) for group in groups.values()), default=0.0)
    consistency = _phase_consistency(rows, field=field, risk_focus_label=definition["risk_focus_label"])
    status = _layer_status(
        float(risk_spread["spread"] or 0.0),
        float(opportunity_spread["spread"] or 0.0),
        str(consistency["phase_consistency"]),
    )
    previous_risk = float(((previous or {}).get("risk_spread") or {}).get("spread") or 0.0)
    previous_opportunity = float(((previous or {}).get("opportunity_spread") or {}).get("spread") or 0.0)
    return {
        "layer_id": definition["layer_id"],
        "layer_name": definition["layer_name"],
        "source": definition["source"],
        "field": field,
        "risk_focus_label": definition["risk_focus_label"],
        "sample_count": len(rows),
        "coverage_rate": coverage,
        "top_group": top_group,
        "top_group_share": round(top_share, 6),
        "risk_spread": risk_spread,
        "drawdown_spread": drawdown_spread,
        "contradiction_spread": contradiction_spread,
        "opportunity_spread": opportunity_spread,
        "phase_consistency": consistency,
        "value_added_vs_previous": {
            "risk_spread_delta": round(float(risk_spread["spread"] or 0.0) - previous_risk, 6),
            "opportunity_spread_delta": round(float(opportunity_spread["spread"] or 0.0) - previous_opportunity, 6),
        },
        "status": status,
        "retention_recommendation": _retention(definition["layer_id"], status),
        "group_metrics": groups,
    }


def _time_safety(rows: Sequence[Mapping[str, object]], source: Mapping[str, object]) -> dict[str, object]:
    violations = [
        {"date": row.get("date"), **violation}
        for row in rows
        for violation in ((row.get("data_quality") or {}).get("time_safety_violations") or [])
    ]
    source_time_safety = source.get("time_safety") if isinstance(source.get("time_safety"), Mapping) else {}
    return {
        "feature_release_or_source_lte_signal_date": not violations and bool(source_time_safety.get("feature_release_or_source_lte_signal_date", True)),
        "violation_count": len(violations) + int(source_time_safety.get("violation_count") or 0),
        "violation_examples": violations[:10],
        "future_labels_used_for_validation_only": True,
    }


def _review_items(layers: Sequence[Mapping[str, object]], time_safety: Mapping[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append({"type": "time_safety_violation", "severity": "high", "evidence": {"violation_count": time_safety.get("violation_count")}})
    weak_layers = [
        layer["layer_id"]
        for layer in layers
        if layer.get("status") in {"no_clear_incremental_value", "weak_opportunity_value"}
    ]
    if weak_layers:
        items.append({"type": "weak_information_layers", "severity": "medium", "evidence": {"layers": weak_layers}})
    items.append(
        {
            "type": "information_attribution_research_only_do_not_modify_policy",
            "severity": "high",
            "evidence": {"reason": "V6.6 attributes fixed existing layers only; no new model, mapper, exposure, ETF, weight, or trade change."},
        }
    )
    return items


def build_context_information_attribution(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    two_axis_source = _read_json(root / "two_axis_context_validation.json")
    score_source = _read_json(root / "exposure_context_score_audit.json")
    if not isinstance(two_axis_source, Mapping) or not isinstance(two_axis_source.get("rows"), list):
        raise RuntimeError("two_axis_context_validation.json is missing or incomplete.")
    if not isinstance(score_source, Mapping) or not isinstance(score_source.get("rows"), list):
        raise RuntimeError("exposure_context_score_audit.json is missing or incomplete.")
    rows = _joined_rows(
        [row for row in two_axis_source.get("rows") or [] if isinstance(row, Mapping)],
        [row for row in score_source.get("rows") or [] if isinstance(row, Mapping)],
    )
    layers = []
    previous_layer = None
    for definition in LAYER_DEFINITIONS:
        layer = _layer_attribution(rows, definition, previous_layer)
        layers.append(layer)
        previous_layer = layer
    time_safety = _time_safety(rows, two_axis_source)
    review_items = _review_items(layers, time_safety)
    risk_leader = max(layers, key=lambda layer: float((layer.get("risk_spread") or {}).get("spread") or 0.0))
    opportunity_leader = max(layers, key=lambda layer: float((layer.get("opportunity_spread") or {}).get("spread") or 0.0))
    retained = [layer for layer in layers if str(layer.get("retention_recommendation") or "").startswith("keep")]
    summary = {
        "joined_sample_count": len(rows),
        "layer_count": len(layers),
        "risk_leader": risk_leader["layer_id"],
        "risk_leader_spread": risk_leader["risk_spread"]["spread"],
        "opportunity_leader": opportunity_leader["layer_id"],
        "opportunity_leader_spread": opportunity_leader["opportunity_spread"]["spread"],
        "retained_layer_count": len(retained),
        "retained_layers": [layer["layer_id"] for layer in retained],
        "ready_for_mapper_change": False,
        "ready_for_exposure_change": False,
        "conclusion": "risk_layers_have_research_value_opportunity_layer_not_ready",
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": "V6.6 attributes information value across fixed layers and does not create or modify any policy rule.",
    }
    return {
        "metadata": {
            "engine": "V6.6 Adaptive Context Information Attribution Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (two_axis_source.get("metadata") or {}).get("as_of"),
            "source_two_axis_engine": (two_axis_source.get("metadata") or {}).get("engine"),
            "source_context_score_engine": (score_source.get("metadata") or {}).get("engine"),
            "purpose": "Attribute which fixed V5-V6 context layers add research value without changing strategy.",
        },
        "summary": summary,
        "layer_attribution": layers,
        "sample_distribution": {
            "market_phase": _distribution(row.get("market_phase") for row in rows),
            "future_environment": _distribution(row.get("future_environment") for row in rows),
        },
        "rows": rows,
        "time_safety": time_safety,
        "data_quality": {
            "uses_fixed_v5_1_exposure_level": True,
            "uses_fixed_v5_10_risk_gradient": True,
            "uses_fixed_v6_3_protection_score": True,
            "uses_fixed_v6_5_two_axis_context": True,
            "future_labels_used_for_validation_only": True,
            "no_new_model": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "audit_only": True,
            "does_not_create_new_model": True,
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


def write_context_information_attribution(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
