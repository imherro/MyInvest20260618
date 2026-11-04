from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean, median
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "exposure_context_state_audit.json"

CONTEXT_STATES = (
    "BALANCED_RECOVERY",
    "BALANCED_STRUCTURAL_OPPORTUNITY",
    "BALANCED_RISK",
    "BALANCED_NEUTRAL",
)
NUMERIC_FIELDS = (
    "macro_score",
    "macro_confidence",
    "credit_score",
    "economy_score",
    "M1_M2_spread",
    "PMI",
    "trend_score",
    "breadth_score",
    "liquidity_score",
    "crowding_score",
    "price_extension_proxy",
)

LOW_SCORE = 40.0
SUPPORTIVE_SCORE = 55.0
HIGH_SCORE = 60.0
PMI_EXPANSION_LINE = 50.0


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


def _context(row: Mapping[str, object]) -> Mapping[str, object]:
    context = row.get("analysis_context")
    return context if isinstance(context, Mapping) else {}


def _number(row: Mapping[str, object], field: str) -> float | None:
    return _to_float(_context(row).get(field))


def _evidence(row: Mapping[str, object]) -> list[str]:
    context = _context(row)
    evidence: list[str] = []
    opportunity_state = str(context.get("opportunity_state") or "")
    risk_state = str(context.get("risk_state") or "")
    macro_score = _number(row, "macro_score")
    credit = _number(row, "credit_score")
    economy = _number(row, "economy_score")
    m1_m2 = _number(row, "M1_M2_spread")
    pmi = _number(row, "PMI")
    trend = _number(row, "trend_score")
    breadth = _number(row, "breadth_score")
    liquidity = _number(row, "liquidity_score")
    crowding = _number(row, "crowding_score")
    extension = _number(row, "price_extension_proxy")

    if opportunity_state == "EARLY_RECOVERY":
        evidence.append("early_recovery")
    if opportunity_state == "STRUCTURAL_ROTATION":
        evidence.append("structural_rotation")
    if risk_state == "NORMAL":
        evidence.append("risk_normal")
    if risk_state == "CROWDED":
        evidence.append("risk_crowded")
    if macro_score is not None and macro_score >= HIGH_SCORE:
        evidence.append("macro_supportive")
    if economy is not None and economy >= PMI_EXPANSION_LINE:
        evidence.append("economy_supportive")
    if pmi is not None and pmi >= PMI_EXPANSION_LINE:
        evidence.append("pmi_expansion")
    if credit is not None and credit >= PMI_EXPANSION_LINE and (m1_m2 is None or m1_m2 >= -2):
        evidence.append("credit_not_weak")
    if (credit is not None and credit < PMI_EXPANSION_LINE) or (m1_m2 is not None and m1_m2 <= -2):
        evidence.append("credit_or_m1m2_weak")
    if trend is not None and trend >= SUPPORTIVE_SCORE:
        evidence.append("trend_supportive")
    if breadth is not None and breadth < LOW_SCORE:
        evidence.append("breadth_low")
    if liquidity is not None and liquidity < LOW_SCORE:
        evidence.append("liquidity_weak")
    if liquidity is not None and liquidity >= LOW_SCORE:
        evidence.append("liquidity_ok")
    if crowding is not None and crowding >= HIGH_SCORE:
        evidence.append("crowding_high")
    if extension is not None and extension >= HIGH_SCORE:
        evidence.append("price_extended")
    return evidence


def classify_context_state(row: Mapping[str, object]) -> tuple[str, list[str]]:
    evidence = _evidence(row)
    source_candidate = str(row.get("candidate") or "")
    structural_rotation = "structural_rotation" in evidence
    risk_crowded = "risk_crowded" in evidence or "crowding_high" in evidence
    price_extended = "price_extended" in evidence
    market_weak = "breadth_low" in evidence or "liquidity_weak" in evidence
    credit_weak = "credit_or_m1m2_weak" in evidence

    if structural_rotation and (
        "trend_supportive" in evidence
        or market_weak
        or price_extended
        or source_candidate == "BALANCED_OPPORTUNITY"
    ):
        return "BALANCED_STRUCTURAL_OPPORTUNITY", evidence
    if source_candidate == "BALANCED_RISK" or (
        (risk_crowded or price_extended)
        and (market_weak or credit_weak)
    ):
        return "BALANCED_RISK", evidence
    if (
        "early_recovery" in evidence
        and "macro_supportive" in evidence
        and "economy_supportive" in evidence
        and "credit_not_weak" in evidence
        and not price_extended
    ):
        return "BALANCED_RECOVERY", evidence
    return "BALANCED_NEUTRAL", evidence


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
    violations = []
    trace_map = row.get("source_trace") if isinstance(row.get("source_trace"), Mapping) else {}
    for field, trace in trace_map.items():
        if not isinstance(trace, Mapping) or trace.get("available") is not True:
            continue
        for key in ("source_date", "release_date", "effective_date"):
            value = trace.get(key)
            if value is not None and str(value) > signal_date:
                violations.append({"field": field, key: value, "signal_date": signal_date})
    return not violations, violations


def _audit_row(row: Mapping[str, object]) -> dict[str, object] | None:
    date_text = _date_text(row.get("date"))
    if not date_text:
        return None
    state, evidence = classify_context_state(row)
    time_safe, violations = _row_time_safety(row)
    context = _context(row)
    return {
        "date": date_text,
        "context_state": state,
        "research_candidate_only": True,
        "source_candidate": row.get("candidate"),
        "outcome": _outcome_label(row),
        "evidence": evidence,
        "analysis_context": {
            "opportunity_state": context.get("opportunity_state"),
            "risk_state": context.get("risk_state"),
            "market_phase": context.get("market_phase"),
            "macro_state": context.get("macro_state"),
            **{field: context.get(field) for field in NUMERIC_FIELDS},
        },
        "future_label": row.get("future_label"),
        "source_trace": row.get("source_trace"),
        "data_quality": {
            "time_safe": time_safe,
            "time_safety_violations": violations,
            "future_label_not_used_for_state_assignment": True,
        },
    }


def _values(rows: Sequence[Mapping[str, object]], field: str) -> list[float]:
    values = []
    for row in rows:
        context = row.get("analysis_context") if isinstance(row.get("analysis_context"), Mapping) else {}
        value = _to_float(context.get(field))
        if value is not None:
            values.append(value)
    return values


def _stats(rows: Sequence[Mapping[str, object]], field: str) -> dict[str, object]:
    values = _values(rows, field)
    if not values:
        return {"available_count": 0, "coverage_rate": 0.0, "avg": None, "median": None}
    return {
        "available_count": len(values),
        "coverage_rate": _share(len(values), len(rows)),
        "avg": round(mean(values), 4),
        "median": round(median(values), 4),
    }


def _stability(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    years = sorted({str(row.get("date"))[:4] for row in rows if _date_text(row.get("date"))})
    if len(rows) >= 20 and len(years) >= 4:
        label = "medium"
    elif len(rows) >= 8 and len(years) >= 2:
        label = "low_medium"
    else:
        label = "low"
    return {"label": label, "year_count": len(years), "years": years}


def _confidence(rows: Sequence[Mapping[str, object]], stability: Mapping[str, object]) -> str:
    if not rows:
        return "low"
    coverage_fields = ("macro_score", "trend_score", "breadth_score", "liquidity_score", "price_extension_proxy")
    coverage = mean(float(_stats(rows, field)["coverage_rate"]) for field in coverage_fields)
    if len(rows) >= 20 and coverage >= 0.65 and stability.get("label") == "medium":
        return "medium"
    if len(rows) >= 8 and coverage >= 0.45:
        return "low_medium"
    return "low"


def _state_quality(state: str, rows: Sequence[Mapping[str, object]], total: int) -> dict[str, object]:
    failure_count = sum(1 for row in rows if row.get("outcome") == "failure")
    opportunity_count = sum(1 for row in rows if row.get("outcome") == "missed_opportunity")
    stability = _stability(rows)
    return {
        "context_state": state,
        "research_candidate_only": True,
        "sample_count": len(rows),
        "share_of_balanced": _share(len(rows), total),
        "future_risk_rate": _share(failure_count, len(rows)),
        "future_opportunity_rate": _share(opportunity_count, len(rows)),
        "outcome_distribution": _distribution(row.get("outcome") for row in rows),
        "source_candidate_distribution": _distribution(row.get("source_candidate") for row in rows),
        "evidence_distribution": _distribution(evidence for row in rows for evidence in (row.get("evidence") or [])),
        "feature_summary": {field: _stats(rows, field) for field in NUMERIC_FIELDS},
        "stability": stability,
        "confidence": _confidence(rows, stability),
        "sample_rows": [
            {
                "date": row.get("date"),
                "outcome": row.get("outcome"),
                "source_candidate": row.get("source_candidate"),
                "evidence": row.get("evidence"),
            }
            for row in rows[:5]
        ],
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


def _field_coverage(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    total = len(rows)
    return {
        field: {
            "available_count": len(_values(rows, field)),
            "missing_count": total - len(_values(rows, field)),
            "coverage_rate": _share(len(_values(rows, field)), total),
        }
        for field in NUMERIC_FIELDS
    }


def _separation_review(rows: Sequence[Mapping[str, object]], state_quality: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    total = len(rows)
    overall_risk = _share(sum(1 for row in rows if row.get("outcome") == "failure"), total)
    overall_opportunity = _share(sum(1 for row in rows if row.get("outcome") == "missed_opportunity"), total)
    risk_payload = state_quality.get("BALANCED_RISK", {})
    opportunity_payload = state_quality.get("BALANCED_STRUCTURAL_OPPORTUNITY", {})
    risk_lift = None
    opportunity_lift = None
    if isinstance(risk_payload.get("future_risk_rate"), (int, float)):
        risk_lift = round(float(risk_payload["future_risk_rate"]) - overall_risk, 6)
    if isinstance(opportunity_payload.get("future_opportunity_rate"), (int, float)):
        opportunity_lift = round(float(opportunity_payload["future_opportunity_rate"]) - overall_opportunity, 6)
    return {
        "overall_future_risk_rate": overall_risk,
        "overall_future_opportunity_rate": overall_opportunity,
        "risk_state_future_risk_lift": risk_lift,
        "structural_opportunity_future_opportunity_lift": opportunity_lift,
        "risk_state_separation": "weak" if risk_lift is None or risk_lift < 0.05 else "visible",
        "opportunity_state_separation": "weak" if opportunity_lift is None or opportunity_lift < 0.05 else "visible",
    }


def _review_items(
    state_quality: Mapping[str, Mapping[str, object]],
    time_safety: Mapping[str, object],
    separation: Mapping[str, object],
) -> list[dict[str, object]]:
    items = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append(
            {
                "type": "time_safety_violation",
                "severity": "high",
                "evidence": {"violation_count": time_safety.get("violation_count")},
            }
        )
    for state, payload in state_quality.items():
        if payload.get("confidence") != "medium":
            items.append(
                {
                    "type": "candidate_state_confidence_not_medium",
                    "severity": "medium",
                    "evidence": {"context_state": state, "confidence": payload.get("confidence")},
                }
            )
    if separation.get("risk_state_separation") == "weak":
        items.append(
            {
                "type": "risk_context_state_edge_weak",
                "severity": "medium",
                "evidence": {"risk_lift": separation.get("risk_state_future_risk_lift")},
            }
        )
    if separation.get("opportunity_state_separation") == "weak":
        items.append(
            {
                "type": "structural_opportunity_edge_weak",
                "severity": "medium",
                "evidence": {"opportunity_lift": separation.get("structural_opportunity_future_opportunity_lift")},
            }
        )
    items.append(
        {
            "type": "research_candidate_only_do_not_modify_mapper",
            "severity": "high",
            "evidence": {"reason": "V5.9 designs candidate context states only; it does not create formal exposure states."},
        }
    )
    return items


def build_exposure_context_state_audit(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    source = _read_json(root / "macro_enhanced_context_analysis.json")
    if not isinstance(source, Mapping) or not isinstance(source.get("rows"), list):
        raise RuntimeError("macro_enhanced_context_analysis.json is missing or incomplete.")

    rows = [
        audited
        for source_row in source.get("rows") or []
        if isinstance(source_row, Mapping)
        for audited in [_audit_row(source_row)]
        if audited is not None
    ]
    grouped = {state: [row for row in rows if row.get("context_state") == state] for state in CONTEXT_STATES}
    state_quality = {state: _state_quality(state, state_rows, len(rows)) for state, state_rows in grouped.items()}
    time_safety = _time_safety(rows)
    separation = _separation_review(rows, state_quality)
    review_items = _review_items(state_quality, time_safety, separation)
    summary = {
        "balanced_usable_rows": len(rows),
        "context_state_distribution": _distribution(row.get("context_state") for row in rows),
        "outcome_distribution": _distribution(row.get("outcome") for row in rows),
        "separation_review": separation,
        "field_coverage": _field_coverage(rows),
        "time_safety": time_safety,
        "ready_for_mapper_change": False,
        "candidate_quality_status": "research_only_not_rule_ready",
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": (
            "BALANCED can be split into research-only context states, but sample confidence is not sufficient "
            "and risk/opportunity separation still needs review before modifying the exposure mapper."
        ),
    }
    return {
        "metadata": {
            "engine": "V5.9 Exposure Context State Model Design Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (source.get("metadata") or {}).get("as_of"),
            "source_engine": (source.get("metadata") or {}).get("engine"),
            "purpose": "Design and audit research-only context-aware BALANCED states without changing exposure rules.",
        },
        "summary": summary,
        "context_state_quality": state_quality,
        "sample_rows": rows[:8],
        "rows": rows,
        "data_quality": {
            "uses_v5_8_macro_enhanced_rows": True,
            "future_labels_used_for_quality_only": True,
            "future_label_not_used_for_state_assignment": True,
            "feature_release_or_source_lte_signal_date": time_safety["feature_release_or_source_lte_signal_date"],
            "missing_values_are_null": True,
            "never_fill_missing_with_zero": True,
        },
        "constraints": {
            "audit_only": True,
            "research_candidates_only": True,
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


def write_exposure_context_state_audit(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
