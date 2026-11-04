from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean, median
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from adaptive_exposure.balanced_context_audit import classify_candidate_context


DEFAULT_OUTPUT_PATH = DATA_DIR / "macro_enhanced_context_analysis.json"

CANDIDATES = ("BALANCED_RISK", "BALANCED_OPPORTUNITY", "BALANCED_NEUTRAL")

MACRO_FIELDS = (
    "macro_score",
    "macro_confidence",
    "credit_score",
    "economy_score",
    "external_score",
    "M1_growth",
    "M2_growth",
    "M1_M2_spread",
    "social_financing_growth",
    "SHIBOR",
    "US10Y",
    "PMI",
    "CPI",
    "PPI",
)
MARKET_FIELDS = ("trend_score", "breadth_score", "liquidity_score", "volatility_score")
THEME_FIELDS = ("industry_breadth", "theme_persistence", "crowding_score", "price_extension_proxy")
NUMERIC_FIELDS = (*MACRO_FIELDS, *MARKET_FIELDS, *THEME_FIELDS)

LOW_SCORE = 40.0
HIGH_SCORE = 60.0
MACRO_WEAK_SCORE = 50.0
PMI_EXPANSION_LINE = 50.0
MEANINGFUL_DELTA = 5.0


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


def _context_key_from_mapping(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("opportunity_state") or "UNKNOWN"),
        str(row.get("risk_state") or "UNKNOWN"),
        str(row.get("market_phase") or "UNKNOWN"),
    )


def _candidate_map(context_analysis: Mapping[str, object]) -> dict[tuple[str, str, str], str]:
    rows = context_analysis.get("context_comparison")
    if not isinstance(rows, list):
        return {}
    mapping = {}
    for row in rows:
        if isinstance(row, Mapping):
            mapping[_context_key_from_mapping(row)] = classify_candidate_context(row)
    return mapping


def _outcome_label(future_label: Mapping[str, object]) -> str:
    if future_label.get("failure"):
        return "failure"
    if future_label.get("missed_opportunity"):
        return "missed_opportunity"
    return "neutral"


def _time_safe_trace(trace: Mapping[str, object], signal_date: str, date_keys: Sequence[str]) -> tuple[bool, list[dict[str, object]]]:
    violations = []
    for key in date_keys:
        value = trace.get(key)
        if value is None:
            continue
        if str(value) > signal_date:
            violations.append({"date_key": key, "value": value, "signal_date": signal_date})
    return not violations, violations


def _value_from_exposure_trace(
    exposure_row: Mapping[str, object],
    field: str,
    signal_date: str,
) -> tuple[float | None, dict[str, object]]:
    exposure_context = exposure_row.get("exposure_context") if isinstance(exposure_row.get("exposure_context"), Mapping) else {}
    trace_map = exposure_row.get("source_trace") if isinstance(exposure_row.get("source_trace"), Mapping) else {}
    trace = trace_map.get(field) if isinstance(trace_map.get(field), Mapping) else {}
    source_date = _date_text(trace.get("source_date"))
    value = _to_float(exposure_context.get(field))
    if source_date and source_date > signal_date:
        return None, {
            "available": False,
            "value": None,
            "source": trace.get("source") or "exposure_numeric_context.json",
            "source_date": source_date,
            "reason": "no_time_safe_source",
            "blocked_future_value": value,
        }
    if value is None:
        return None, {
            "available": False,
            "value": None,
            "source": trace.get("source") or "exposure_numeric_context.json",
            "source_date": source_date,
            "reason": trace.get("reason") or "value_missing",
        }
    return value, {
        "available": True,
        "value": value,
        "source": trace.get("source") or "exposure_numeric_context.json",
        "source_date": source_date,
        "reason": None,
    }


def _value_from_macro_trace(
    macro_row: Mapping[str, object] | None,
    field: str,
    signal_date: str,
) -> tuple[float | None, dict[str, object]]:
    source = "macro_context_history.json/rows"
    if not macro_row:
        return None, {
            "available": False,
            "value": None,
            "source": source,
            "release_date": None,
            "effective_date": None,
            "reason": "macro_context_missing",
        }
    macro_context = macro_row.get("macro_context") if isinstance(macro_row.get("macro_context"), Mapping) else {}
    trace_map = macro_row.get("source_trace") if isinstance(macro_row.get("source_trace"), Mapping) else {}
    trace = trace_map.get(field) if isinstance(trace_map.get(field), Mapping) else {}
    release_date = _date_text(trace.get("release_date"))
    effective_date = _date_text(trace.get("effective_date"))
    time_safe, violations = _time_safe_trace(trace, signal_date, ("release_date", "effective_date"))
    value = _to_float(macro_context.get(field))
    if not time_safe:
        return None, {
            "available": False,
            "value": None,
            "source": trace.get("source") or source,
            "observation_date": trace.get("observation_date"),
            "release_date": release_date,
            "effective_date": effective_date,
            "reason": "no_time_safe_macro_context",
            "blocked_future_value": value,
            "violations": violations,
        }
    if value is None:
        return None, {
            "available": False,
            "value": None,
            "source": trace.get("source") or source,
            "observation_date": trace.get("observation_date"),
            "release_date": release_date,
            "effective_date": effective_date,
            "reason": trace.get("reason") or "value_missing",
        }
    return value, {
        "available": True,
        "value": value,
        "source": trace.get("source") or source,
        "observation_date": trace.get("observation_date"),
        "release_date": release_date,
        "effective_date": effective_date,
        "reason": None,
    }


def _safe_macro_state(macro_row: Mapping[str, object] | None, signal_date: str) -> str | None:
    if not macro_row:
        return None
    macro_context = macro_row.get("macro_context") if isinstance(macro_row.get("macro_context"), Mapping) else {}
    trace_map = macro_row.get("source_trace") if isinstance(macro_row.get("source_trace"), Mapping) else {}
    trace = trace_map.get("macro_state") if isinstance(trace_map.get("macro_state"), Mapping) else {}
    time_safe, _ = _time_safe_trace(trace, signal_date, ("release_date", "effective_date"))
    value = macro_context.get("macro_state")
    return str(value) if time_safe and value is not None else None


def _make_analysis_row(
    exposure_row: Mapping[str, object],
    *,
    macro_by_date: Mapping[str, Mapping[str, object]],
    candidates_by_context: Mapping[tuple[str, str, str], str],
) -> dict[str, object] | None:
    date_text = _date_text(exposure_row.get("date"))
    if not date_text:
        return None
    exposure_context = exposure_row.get("exposure_context") if isinstance(exposure_row.get("exposure_context"), Mapping) else {}
    if exposure_context.get("exposure_level") != "BALANCED":
        return None
    future_label = exposure_row.get("future_label") if isinstance(exposure_row.get("future_label"), Mapping) else {}
    if future_label.get("future_window_complete") is not True:
        return None

    context_key = _context_key_from_mapping(exposure_context)
    candidate = candidates_by_context.get(context_key, "BALANCED_NEUTRAL")
    macro_row = macro_by_date.get(date_text)
    analysis_context: dict[str, object] = {
        "opportunity_state": exposure_context.get("opportunity_state"),
        "risk_state": exposure_context.get("risk_state"),
        "market_phase": exposure_context.get("market_phase"),
        "policy_mode": exposure_context.get("policy_mode"),
        "macro_state": _safe_macro_state(macro_row, date_text),
    }
    source_trace = {}

    for field in MACRO_FIELDS:
        value, trace = _value_from_macro_trace(macro_row, field, date_text)
        analysis_context[field] = value
        source_trace[field] = trace
    for field in (*MARKET_FIELDS, *THEME_FIELDS):
        value, trace = _value_from_exposure_trace(exposure_row, field, date_text)
        analysis_context[field] = value
        source_trace[field] = trace

    missing = [field for field in NUMERIC_FIELDS if analysis_context.get(field) is None]
    return {
        "date": date_text,
        "candidate": candidate,
        "candidate_label_source": "V5.4 context map" if context_key in candidates_by_context else "fallback_unmapped_neutral",
        "outcome": _outcome_label(future_label),
        "future_label": future_label,
        "analysis_context": analysis_context,
        "source_trace": source_trace,
        "data_quality": {
            "available_numeric_fields": [field for field in NUMERIC_FIELDS if analysis_context.get(field) is not None],
            "missing_numeric_fields": missing,
            "null_means_unavailable_not_zero": True,
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
        return {
            "available_count": 0,
            "coverage_rate": 0.0,
            "avg": None,
            "median": None,
            "min": None,
            "max": None,
        }
    return {
        "available_count": len(values),
        "coverage_rate": _share(len(values), len(rows)),
        "avg": round(mean(values), 4),
        "median": round(median(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _feature_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    return {
        "macro": {field: _stats(rows, field) for field in MACRO_FIELDS},
        "market": {field: _stats(rows, field) for field in MARKET_FIELDS},
        "theme": {field: _stats(rows, field) for field in THEME_FIELDS},
    }


def _outcome_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    return {
        outcome: {
            "count": len(group_rows),
            "share": _share(len(group_rows), len(rows)),
            "features": _feature_summary(group_rows),
        }
        for outcome in ("failure", "missed_opportunity", "neutral")
        for group_rows in ([row for row in rows if row.get("outcome") == outcome],)
    }


def _avg(rows: Sequence[Mapping[str, object]], field: str) -> float | None:
    values = _values(rows, field)
    return round(mean(values), 4) if values else None


def _delta(candidate_rows: Sequence[Mapping[str, object]], baseline_rows: Sequence[Mapping[str, object]], field: str) -> float | None:
    candidate_avg = _avg(candidate_rows, field)
    baseline_avg = _avg(baseline_rows, field)
    if candidate_avg is None or baseline_avg is None:
        return None
    return round(candidate_avg - baseline_avg, 4)


def _share_of_context(rows: Sequence[Mapping[str, object]], key: str, value: str) -> float:
    count = sum(
        1
        for row in rows
        if ((row.get("analysis_context") or {}).get(key) if isinstance(row.get("analysis_context"), Mapping) else None) == value
    )
    return _share(count, len(rows))


def _driver_flags(candidate: str, rows: Sequence[Mapping[str, object]], baseline_rows: Sequence[Mapping[str, object]]) -> dict[str, bool]:
    macro_score = _avg(rows, "macro_score")
    credit = _avg(rows, "credit_score")
    economy = _avg(rows, "economy_score")
    pmi = _avg(rows, "PMI")
    m1_m2 = _avg(rows, "M1_M2_spread")
    liquidity = _avg(rows, "liquidity_score")
    breadth = _avg(rows, "breadth_score")
    trend = _avg(rows, "trend_score")
    crowding = _avg(rows, "crowding_score")
    price_extension = _avg(rows, "price_extension_proxy")
    macro_delta = _delta(rows, baseline_rows, "macro_score")
    liquidity_delta = _delta(rows, baseline_rows, "liquidity_score")
    breadth_delta = _delta(rows, baseline_rows, "breadth_score")
    structural_rotation_share = _share_of_context(rows, "opportunity_state", "STRUCTURAL_ROTATION")
    crowded_share = _share_of_context(rows, "risk_state", "CROWDED")

    macro_score_low = macro_score is not None and macro_score < MACRO_WEAK_SCORE
    macro_credit_weak = (credit is not None and credit < MACRO_WEAK_SCORE) or (m1_m2 is not None and m1_m2 <= -2)
    macro_weaker_than_baseline = macro_delta is not None and macro_delta <= -MEANINGFUL_DELTA
    macro_recovery = (
        macro_score is not None
        and macro_score >= MACRO_WEAK_SCORE
        and (pmi is None or pmi >= PMI_EXPANSION_LINE)
        and (credit is None or credit >= MACRO_WEAK_SCORE)
        and (economy is None or economy >= MACRO_WEAK_SCORE)
        and (m1_m2 is None or m1_m2 >= -2)
    )
    liquidity_weak = liquidity is not None and liquidity < LOW_SCORE
    liquidity_below_baseline = liquidity_delta is not None and liquidity_delta <= -MEANINGFUL_DELTA
    liquidity_above_baseline = liquidity_delta is not None and liquidity_delta >= MEANINGFUL_DELTA
    breadth_low = breadth is not None and breadth < LOW_SCORE
    breadth_below_baseline = breadth_delta is not None and breadth_delta <= -MEANINGFUL_DELTA
    trend_weak = trend is not None and trend < LOW_SCORE
    crowding_high = crowded_share >= 0.6 or (crowding is not None and crowding >= HIGH_SCORE)
    price_extended = price_extension is not None and price_extension >= HIGH_SCORE

    flags = {
        "macro_score_low": macro_score_low,
        "macro_credit_weak": macro_credit_weak,
        "macro_weaker_than_balanced_avg": macro_weaker_than_baseline,
        "macro_recovery": macro_recovery,
        "liquidity_weak": liquidity_weak,
        "liquidity_below_balanced_avg": liquidity_below_baseline,
        "liquidity_above_balanced_avg": liquidity_above_baseline,
        "breadth_low": breadth_low,
        "breadth_below_balanced_avg": breadth_below_baseline,
        "trend_weak": trend_weak,
        "crowding_high": crowding_high,
        "price_extended": price_extended,
        "structural_rotation": structural_rotation_share >= 0.3,
    }
    if candidate == "BALANCED_RISK":
        flags["risk_hypothesis_supported"] = any(
            flags[key]
            for key in (
                "macro_score_low",
                "macro_credit_weak",
                "macro_weaker_than_balanced_avg",
                "liquidity_weak",
                "liquidity_below_balanced_avg",
                "breadth_low",
                "breadth_below_balanced_avg",
                "crowding_high",
                "price_extended",
            )
        )
    if candidate == "BALANCED_OPPORTUNITY":
        flags["opportunity_hypothesis_supported"] = any(
            flags[key]
            for key in ("macro_recovery", "liquidity_above_balanced_avg", "structural_rotation")
        )
    return flags


def _driver_evidence(rows: Sequence[Mapping[str, object]], baseline_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    fields = (
        "macro_score",
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
    return {
        field: {
            "candidate_avg": _avg(rows, field),
            "balanced_avg": _avg(baseline_rows, field),
            "delta_vs_balanced": _delta(rows, baseline_rows, field),
            "available_count": len(_values(rows, field)),
        }
        for field in fields
    }


def _confidence(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return "low"
    core_fields = ("macro_score", "trend_score", "breadth_score", "liquidity_score", "industry_breadth")
    available_rates = [_stats(rows, field)["coverage_rate"] for field in core_fields]
    average_coverage = mean(float(rate) for rate in available_rates) if available_rates else 0.0
    if len(rows) >= 20 and average_coverage >= 0.7:
        return "medium"
    if len(rows) >= 10 and average_coverage >= 0.45:
        return "low_medium"
    return "low"


def _interpretation(candidate: str, flags: Mapping[str, bool]) -> str:
    if candidate == "BALANCED_RISK":
        if flags.get("risk_hypothesis_supported"):
            return "risk_candidate_has_macro_or_market_weakness_evidence_but_not_rule_ready"
        return "risk_candidate_still_lacks_numeric_driver_confirmation"
    if candidate == "BALANCED_OPPORTUNITY":
        if flags.get("opportunity_hypothesis_supported"):
            return "opportunity_candidate_has_recovery_or_rotation_evidence_but_not_rule_ready"
        return "opportunity_candidate_still_lacks_numeric_driver_confirmation"
    return "neutral_candidate_remains_mixed_after_macro_enrichment"


def _candidate_payload(
    candidate: str,
    rows: Sequence[Mapping[str, object]],
    baseline_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    failure_count = sum(1 for row in rows if row.get("outcome") == "failure")
    opportunity_count = sum(1 for row in rows if row.get("outcome") == "missed_opportunity")
    flags = _driver_flags(candidate, rows, baseline_rows)
    return {
        "candidate": candidate,
        "sample_count": len(rows),
        "share_of_balanced": _share(len(rows), len(baseline_rows)),
        "future_failure_rate": _share(failure_count, len(rows)),
        "future_opportunity_rate": _share(opportunity_count, len(rows)),
        "outcome_distribution": _distribution(row.get("outcome") for row in rows),
        "context_distribution": {
            "opportunity_state": _distribution((row.get("analysis_context") or {}).get("opportunity_state") for row in rows),
            "risk_state": _distribution((row.get("analysis_context") or {}).get("risk_state") for row in rows),
            "market_phase": _distribution((row.get("analysis_context") or {}).get("market_phase") for row in rows),
            "macro_state": _distribution((row.get("analysis_context") or {}).get("macro_state") for row in rows),
        },
        "drivers": flags,
        "driver_evidence": _driver_evidence(rows, baseline_rows),
        "feature_summary": _feature_summary(rows),
        "outcome_contrast": _outcome_summary(rows),
        "confidence": _confidence(rows),
        "interpretation": _interpretation(candidate, flags),
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


def _time_safety(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    checked = 0
    violations = []
    blocked_future_values = 0
    for row in rows:
        signal_date = str(row.get("date") or "")
        trace_map = row.get("source_trace") if isinstance(row.get("source_trace"), Mapping) else {}
        for field, trace in trace_map.items():
            if not isinstance(trace, Mapping):
                continue
            if trace.get("blocked_future_value") is not None:
                blocked_future_values += 1
            for key in ("source_date", "release_date", "effective_date"):
                value = trace.get(key)
                if value is None:
                    continue
                checked += 1
                if str(value) > signal_date and trace.get("available") is True:
                    violations.append({"date": signal_date, "field": field, key: value})
    return {
        "feature_release_or_source_lte_signal_date": not violations,
        "checked_values": checked,
        "violation_count": len(violations),
        "blocked_future_values": blocked_future_values,
        "violation_examples": violations[:10],
        "no_future_fill": True,
    }


def _review_items(candidate_payloads: Mapping[str, Mapping[str, object]], time_safety: Mapping[str, object]) -> list[dict[str, object]]:
    items = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append(
            {
                "type": "time_safety_violation",
                "severity": "high",
                "evidence": {"violation_count": time_safety.get("violation_count")},
            }
        )
    for candidate, payload in candidate_payloads.items():
        if payload.get("confidence") != "medium":
            items.append(
                {
                    "type": "candidate_confidence_not_medium",
                    "severity": "medium",
                    "evidence": {"candidate": candidate, "confidence": payload.get("confidence")},
                }
            )
    items.append(
        {
            "type": "do_not_modify_mapper_yet",
            "severity": "high",
            "evidence": {"reason": "V5.8 is attribution-only; drivers are hypotheses, not formal exposure rules."},
        }
    )
    return items


def _macro_added_value(candidate_payloads: Mapping[str, Mapping[str, object]]) -> str:
    risk_flags = candidate_payloads.get("BALANCED_RISK", {}).get("drivers") or {}
    opportunity_flags = candidate_payloads.get("BALANCED_OPPORTUNITY", {}).get("drivers") or {}
    if risk_flags.get("macro_score_low") or risk_flags.get("macro_credit_weak") or opportunity_flags.get("macro_recovery"):
        return "visible_but_not_rule_ready"
    return "limited"


def build_macro_enhanced_context_analysis(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    exposure_numeric = _read_json(root / "exposure_numeric_context.json")
    macro_history = _read_json(root / "macro_context_history.json")
    context_analysis = _read_json(root / "exposure_context_analysis.json")
    balanced_audit = _read_json(root / "balanced_context_audit.json")
    if not all(isinstance(item, Mapping) for item in (exposure_numeric, macro_history, context_analysis, balanced_audit)):
        raise RuntimeError("Required V5.3/V5.4/V5.6/V5.7 artifacts are missing.")

    exposure_rows = exposure_numeric.get("rows")
    macro_rows = macro_history.get("rows")
    if not isinstance(exposure_rows, list) or not isinstance(macro_rows, list):
        raise RuntimeError("exposure_numeric_context.json or macro_context_history.json is incomplete.")

    macro_by_date = {
        str(row.get("date")): row
        for row in macro_rows
        if isinstance(row, Mapping) and _date_text(row.get("date"))
    }
    candidates_by_context = _candidate_map(context_analysis)
    rows = [
        row
        for source_row in exposure_rows
        for row in [_make_analysis_row(source_row, macro_by_date=macro_by_date, candidates_by_context=candidates_by_context)]
        if row is not None
    ]
    grouped = {candidate: [row for row in rows if row.get("candidate") == candidate] for candidate in CANDIDATES}
    candidate_payloads = {
        candidate: _candidate_payload(candidate, candidate_rows, rows)
        for candidate, candidate_rows in grouped.items()
    }
    time_safety = _time_safety(rows)
    review_items = _review_items(candidate_payloads, time_safety)
    unmapped_contexts = sum(1 for row in rows if row.get("candidate_label_source") != "V5.4 context map")
    summary = {
        "balanced_usable_rows": len(rows),
        "candidate_distribution": _distribution(row.get("candidate") for row in rows),
        "outcome_distribution": _distribution(row.get("outcome") for row in rows),
        "macro_added_explanatory_value": _macro_added_value(candidate_payloads),
        "field_coverage": _field_coverage(rows),
        "time_safety": time_safety,
        "unmapped_context_count": unmapped_contexts,
        "ready_for_rule_change": False,
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": (
            "Macro-enhanced attribution adds macro, market, and theme numeric context to fixed V5.4 BALANCED candidates; "
            "it improves diagnosis but remains attribution-only and does not justify mapper changes yet."
        ),
    }
    return {
        "metadata": {
            "engine": "V5.8 Macro-Enhanced Exposure Context Re-Attribution",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (exposure_numeric.get("metadata") or {}).get("as_of"),
            "source_engine": (exposure_numeric.get("metadata") or {}).get("engine"),
            "purpose": "Re-attribute fixed V5.4 BALANCED research candidates with V5.6 numeric context and V5.7 macro context without changing rules.",
        },
        "summary": summary,
        "candidate_re_attribution": candidate_payloads,
        "sample_rows": rows[:8],
        "rows": rows,
        "data_quality": {
            "uses_fixed_v5_4_candidate_labels": True,
            "candidate_label_source": "balanced_context_audit / classify_candidate_context over V5.3 context rows",
            "uses_v5_6_numeric_context": True,
            "uses_v5_7_macro_context": True,
            "future_labels_used_for_attribution_only": True,
            "feature_release_or_source_lte_signal_date": time_safety["feature_release_or_source_lte_signal_date"],
            "missing_values_are_null": True,
            "never_fill_missing_with_zero": True,
            "does_not_reclassify_candidates": True,
        },
        "constraints": {
            "audit_only": True,
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


def write_macro_enhanced_context_analysis(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
