from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_gradient_candidate_rules.json"

PERIODS = (
    ("2015-2017", "20150101", "20171231"),
    ("2018", "20180101", "20181231"),
    ("2020", "20200101", "20201231"),
    ("2021", "20210101", "20211231"),
    ("2022", "20220101", "20221231"),
    ("2024-2026", "20240101", "20261231"),
)


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
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _rate(rows: Sequence[Mapping[str, object]], outcome: str = "failure") -> float:
    return _share(sum(1 for row in rows if row.get("outcome") == outcome), len(rows))


def _context_value(row: Mapping[str, object], field: str) -> str:
    context = row.get("analysis_context")
    if not isinstance(context, Mapping):
        return "UNKNOWN"
    return str(context.get(field) or "UNKNOWN")


def _candidate_fields(condition_type: object) -> list[str]:
    text = str(condition_type or "")
    if ":" not in text:
        return []
    return text.split(":", 1)[1].split("+")


def _candidate_values(condition: object) -> list[str]:
    return str(condition or "").split("+") if condition else []


def _matches(row: Mapping[str, object], fields: Sequence[str], values: Sequence[str]) -> bool:
    return len(fields) == len(values) and all(_context_value(row, field) == value for field, value in zip(fields, values))


def _period_status(rows: Sequence[Mapping[str, object]], trigger_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    base_rate = _rate(rows, "failure") if rows else None
    trigger_rate = _rate(trigger_rows, "failure") if trigger_rows else None
    lift = round(trigger_rate - base_rate, 6) if trigger_rate is not None and base_rate is not None else None
    if len(rows) < 6:
        status = "insufficient_total_sample"
    elif len(trigger_rows) < 3:
        status = "insufficient_trigger_sample"
    elif lift is not None and lift >= 0.05:
        status = "positive"
    elif lift is not None and lift <= -0.05:
        status = "negative"
    else:
        status = "flat"
    return {
        "sample_count": len(rows),
        "trigger_sample_count": len(trigger_rows),
        "base_failure_rate": base_rate,
        "trigger_failure_rate": trigger_rate,
        "lift": lift,
        "status": status,
    }


def _period_coverage(matched_rows: Sequence[Mapping[str, object]], trigger_rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    coverage = []
    for name, start, end in PERIODS:
        period_rows = [row for row in matched_rows if (date := _date_text(row.get("date"))) and start <= date <= end]
        period_triggers = [row for row in trigger_rows if (date := _date_text(row.get("date"))) and start <= date <= end]
        stats = _period_status(period_rows, period_triggers)
        coverage.append({"period": name, "start_date": start, "end_date": end, **stats})
    return coverage


def _stability(coverage: Sequence[Mapping[str, object]]) -> dict[str, object]:
    evaluated = [item for item in coverage if item.get("status") in {"positive", "negative", "flat"}]
    positive = [item for item in evaluated if item.get("status") == "positive"]
    negative = [item for item in evaluated if item.get("status") == "negative"]
    insufficient = [item for item in coverage if str(item.get("status") or "").startswith("insufficient")]
    if len(evaluated) < 3:
        label = "insufficient_evidence"
    elif len(negative) == 0 and _share(len(positive), len(evaluated)) >= 0.67:
        label = "medium"
    else:
        label = "weak"
    return {
        "label": label,
        "evaluated_period_count": len(evaluated),
        "positive_period_count": len(positive),
        "negative_period_count": len(negative),
        "insufficient_period_count": len(insufficient),
        "positive_periods": [item.get("period") for item in positive],
        "negative_periods": [item.get("period") for item in negative],
    }


def _research_tier(candidate_ref: Mapping[str, object], stability: Mapping[str, object]) -> str:
    sample_count = int(candidate_ref.get("sample_count") or 0)
    trigger_count = int(candidate_ref.get("high_risk_sample_count") or 0)
    lift = float(candidate_ref.get("high_risk_lift") or 0.0)
    condition = str(candidate_ref.get("condition") or "")
    if sample_count >= 30 and trigger_count >= 5 and lift >= 0.15 and condition in {"CROWDED", "EARLY_CYCLE+CROWDED"}:
        return "primary_research_candidate"
    if sample_count >= 15 and trigger_count >= 5 and lift >= 0.10:
        return "secondary_watch_candidate"
    return "low_priority_candidate"


def _rule_candidate(rule_id: str, candidate_ref: Mapping[str, object], rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    fields = _candidate_fields(candidate_ref.get("condition_type"))
    values = _candidate_values(candidate_ref.get("condition"))
    matched_rows = [row for row in rows if _matches(row, fields, values)]
    trigger_rows = [row for row in matched_rows if row.get("risk_gradient_bucket") == "high_risk"]
    coverage = _period_coverage(matched_rows, trigger_rows)
    stability = _stability(coverage)
    tier = _research_tier(candidate_ref, stability)
    base_failure_rate = _rate(matched_rows, "failure")
    trigger_failure_rate = _rate(trigger_rows, "failure") if trigger_rows else None
    lift = round(trigger_failure_rate - base_failure_rate, 6) if trigger_failure_rate is not None else None
    return {
        "rule_id": rule_id,
        "candidate": candidate_ref.get("condition"),
        "source_condition_type": candidate_ref.get("condition_type"),
        "fields": fields,
        "values": values,
        "trigger": "risk_gradient_bucket == high_risk",
        "sample_count": len(matched_rows),
        "trigger_sample_count": len(trigger_rows),
        "base_failure_rate": base_failure_rate,
        "trigger_failure_rate": trigger_failure_rate,
        "high_risk_lift": lift,
        "period_coverage": coverage,
        "stability": stability,
        "research_tier": tier,
        "worth_continuing_research": tier in {"primary_research_candidate", "secondary_watch_candidate"},
        "ready_for_rule": False,
        "not_rule_ready_reasons": [
            "research_only_candidate",
            "period_stability_not_strong_enough",
            "no_exposure_or_return_backtest",
            "small_trigger_samples_in_multiple_periods",
        ],
        "outcome_distribution": _distribution(row.get("outcome") for row in matched_rows),
        "trigger_sample_rows": [
            {
                "date": row.get("date"),
                "outcome": row.get("outcome"),
                "risk_gradient_score": row.get("risk_gradient_score"),
                "opportunity_state": _context_value(row, "opportunity_state"),
                "market_phase": _context_value(row, "market_phase"),
                "risk_state": _context_value(row, "risk_state"),
            }
            for row in trigger_rows[:10]
        ],
    }


def _time_safety(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    violations = [
        {"date": row.get("date"), **violation}
        for row in rows
        for violation in ((row.get("data_quality") or {}).get("time_safety_violations") or [])
    ]
    return {
        "feature_release_or_source_lte_signal_date": not violations,
        "violation_count": len(violations),
        "violation_examples": violations[:10],
        "future_labels_used_for_validation_only": True,
        "risk_gradient_score_is_precomputed_v5_10": True,
    }


def _review_items(candidates: Sequence[Mapping[str, object]], time_safety: Mapping[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append({"type": "time_safety_violation", "severity": "high", "evidence": {"violation_count": time_safety.get("violation_count")}})
    primary = [item for item in candidates if item.get("research_tier") == "primary_research_candidate"]
    if primary:
        items.append(
            {
                "type": "minimal_primary_candidates_found",
                "severity": "medium",
                "evidence": [{"rule_id": item.get("rule_id"), "candidate": item.get("candidate"), "lift": item.get("high_risk_lift")} for item in primary],
            }
        )
    if not any(item.get("ready_for_rule") for item in candidates):
        items.append(
            {
                "type": "no_candidate_rule_ready",
                "severity": "high",
                "evidence": {"reason": "All candidates lack enough period stability for formal rules."},
            }
        )
    items.append(
        {
            "type": "candidate_audit_research_only_do_not_modify_mapper",
            "severity": "high",
            "evidence": {"reason": "V5.13 audits minimal candidates only; no mapper, exposure, ETF, trade, or parameter search."},
        }
    )
    return items


def build_risk_gradient_candidate_rules(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    gradient_source = _read_json(root / "exposure_gradient_analysis.json")
    condition_source = _read_json(root / "risk_gradient_condition_analysis.json")
    if not isinstance(gradient_source, Mapping) or not isinstance(gradient_source.get("rows"), list):
        raise RuntimeError("exposure_gradient_analysis.json is missing or incomplete.")
    if not isinstance(condition_source, Mapping):
        raise RuntimeError("risk_gradient_condition_analysis.json is missing or incomplete.")
    rows = [row for row in gradient_source.get("rows") or [] if isinstance(row, Mapping) and _date_text(row.get("date"))]
    top_positive = (condition_source.get("summary") or {}).get("top_positive_conditions")
    if not isinstance(top_positive, list) or not top_positive:
        raise RuntimeError("V5.12 top_positive_conditions missing; cannot build minimal candidates.")
    source_candidates = [item for item in top_positive[:5] if isinstance(item, Mapping)]
    candidates = [
        _rule_candidate(f"R{index}", candidate, rows)
        for index, candidate in enumerate(source_candidates, start=1)
    ]
    time_safety = _time_safety(rows)
    review_items = _review_items(candidates, time_safety)
    primary = [item for item in candidates if item.get("research_tier") == "primary_research_candidate"]
    secondary = [item for item in candidates if item.get("research_tier") == "secondary_watch_candidate"]
    summary = {
        "source_rows": len(rows),
        "source_candidate_count": len(source_candidates),
        "candidate_count": len(candidates),
        "primary_research_candidate_count": len(primary),
        "secondary_watch_candidate_count": len(secondary),
        "ready_for_rule_count": sum(1 for item in candidates if item.get("ready_for_rule") is True),
        "recommended_research_candidates": [
            {"rule_id": item.get("rule_id"), "candidate": item.get("candidate"), "tier": item.get("research_tier"), "lift": item.get("high_risk_lift")}
            for item in primary + secondary
        ],
        "ready_for_mapper_change": False,
        "conclusion": "minimal_candidates_found_but_none_rule_ready",
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": (
            "A small candidate set exists, led by CROWDED and EARLY_CYCLE+CROWDED, "
            "but every candidate remains research-only because period stability is not strong enough."
        ),
    }
    return {
        "metadata": {
            "engine": "V5.13 Risk Gradient Minimal Rule Candidate Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (gradient_source.get("metadata") or {}).get("as_of"),
            "source_engine": (condition_source.get("metadata") or {}).get("engine"),
            "purpose": "Audit a small set of V5.12-derived risk candidates without creating formal rules.",
        },
        "summary": summary,
        "candidate_rules": candidates,
        "time_safety": time_safety,
        "data_quality": {
            "uses_v5_12_positive_conditions_only": True,
            "candidate_count_limited": True,
            "does_not_search_condition_space": True,
            "risk_gradient_score_reused_not_reweighted": True,
            "future_labels_used_for_validation_only": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "audit_only": True,
            "no_formal_rule_output": True,
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


def write_risk_gradient_candidate_rules(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
