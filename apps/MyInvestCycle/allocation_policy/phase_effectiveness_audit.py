from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from allocation_policy.phase_transition_analysis import analyze_phase_transitions
from allocation_policy.policy_historical_validation import DEFAULT_PERIODS


DEFAULT_OUTPUT_PATH = DATA_DIR / "phase_effectiveness.json"


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _joined_rows(market_phase: Mapping[str, object], policy_effectiveness: Mapping[str, object]) -> list[dict[str, object]]:
    phase_rows = {
        str(row.get("date") or ""): row
        for row in market_phase.get("historical_replay") or []
        if isinstance(row, Mapping)
    }
    joined = []
    for row in policy_effectiveness.get("validation_rows") or []:
        if not isinstance(row, Mapping) or not row.get("future_window_complete"):
            continue
        date_text = str(row.get("date") or "")
        phase_row = phase_rows.get(date_text)
        if not phase_row:
            continue
        joined.append(
            {
                "date": date_text,
                "phase": phase_row.get("phase"),
                "phase_evidence": phase_row.get("evidence") or [],
                "structural_state": row.get("structural_state"),
                "combined_state": row.get("combined_state"),
                "policy_mode": row.get("policy_mode"),
                "future_environment": row.get("future_environment"),
                "future_flags": row.get("future_flags") or {},
                "future_metrics": row.get("future_metrics") or {},
                "policy_alignment": row.get("policy_alignment"),
                "contradictions": row.get("contradictions") or [],
            }
        )
    return joined


def _rate(rows: Sequence[Mapping[str, object]], flag_key: str) -> float:
    if not rows:
        return 0.0
    return _share(sum(1 for row in rows if _section(row, "future_flags").get(flag_key)), len(rows))


def _phase_group_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("phase") or "UNKNOWN")].append(row)
    return {
        phase: {
            "count": len(items),
            "high_risk_event_rate": _rate(items, "high_risk_event"),
            "strong_opportunity_rate": _rate(items, "strong_opportunity_event"),
            "future_environment_distribution": _distribution(row.get("future_environment") for row in items),
        }
        for phase, items in sorted(grouped.items())
    }


def _phase_spread(groups: Mapping[str, Mapping[str, object]]) -> float:
    rates = [
        float(item.get("high_risk_event_rate") or 0.0)
        for item in groups.values()
        if int(item.get("count") or 0) >= 3
    ]
    return round(max(rates) - min(rates), 6) if rates else 0.0


def _period_rows(rows: Sequence[Mapping[str, object]], period: Mapping[str, object]) -> list[Mapping[str, object]]:
    start = str(period["start"])
    end = str(period["end"])
    return [row for row in rows if start <= str(row.get("date") or "") <= end]


def _period_error_cases(period: Mapping[str, object], rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    period_id = str(period.get("id") or "")
    candidates = _period_rows(rows, period)
    cases = []
    for row in candidates:
        flags = _section(row, "future_flags")
        phase = str(row.get("phase") or "UNKNOWN")
        if period_id in {"2018_bear", "2022_bear"} and flags.get("high_risk_event") and phase not in {
            "CONTRACTION",
            "LATE_CYCLE",
        }:
            cases.append(
                {
                    "date": row.get("date"),
                    "type": "bear_period_high_risk_not_contraction_or_late",
                    "phase": phase,
                    "future_environment": row.get("future_environment"),
                    "metrics": _case_metrics(row),
                }
            )
        if period_id == "2024_2026_structural" and phase == "CONTRACTION" and flags.get("strong_opportunity_event"):
            cases.append(
                {
                    "date": row.get("date"),
                    "type": "structural_period_contraction_before_opportunity",
                    "phase": phase,
                    "future_environment": row.get("future_environment"),
                    "metrics": _case_metrics(row),
                }
            )
        if phase == "LATE_CYCLE" and flags.get("strong_opportunity_event"):
            cases.append(
                {
                    "date": row.get("date"),
                    "type": "late_cycle_before_opportunity_review",
                    "phase": phase,
                    "future_environment": row.get("future_environment"),
                    "metrics": _case_metrics(row),
                }
            )
    return {
        "period": period.get("id"),
        "label": period.get("label"),
        "usable_rows": len(candidates),
        "phase_distribution": _distribution(row.get("phase") for row in candidates),
        "future_environment_distribution": _distribution(row.get("future_environment") for row in candidates),
        "error_case_count": len(cases),
        "sample_error_cases": cases[:10],
    }


def _case_metrics(row: Mapping[str, object]) -> dict[str, object]:
    metrics = _section(row, "future_metrics")
    return {
        "forward_return_120d": metrics.get("forward_return_120d"),
        "max_drawdown_120d": metrics.get("max_drawdown_120d"),
        "max_drawdown_60d": metrics.get("max_drawdown_60d"),
    }


def _calibration_review_items(
    market_phase: Mapping[str, object],
    phase_groups: Mapping[str, Mapping[str, object]],
    model_comparison: Mapping[str, object],
    period_cases: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    items = []
    phase_spread = float(model_comparison.get("phase_high_risk_rate_spread") or 0.0)
    structural_spread = float(model_comparison.get("structural_high_risk_rate_spread") or 0.0)
    if phase_spread <= structural_spread:
        items.append(
            {
                "type": "phase_not_better_than_structural",
                "severity": "high",
                "evidence": {
                    "phase_high_risk_rate_spread": phase_spread,
                    "structural_high_risk_rate_spread": structural_spread,
                },
            }
        )
    phase_distribution = _section(_section(market_phase, "historical_summary"), "phase_distribution")
    expansion_count = int(_section(phase_distribution, "EXPANSION").get("count") or 0)
    replay_count = int(_section(market_phase, "historical_summary").get("replay_count") or 0)
    if replay_count and expansion_count / replay_count <= 0.05:
        items.append(
            {
                "type": "expansion_sample_too_sparse",
                "severity": "medium",
                "evidence": {"expansion_count": expansion_count, "replay_count": replay_count},
            }
        )
    late_cycle = phase_groups.get("LATE_CYCLE") or {}
    early_cycle = phase_groups.get("EARLY_CYCLE") or {}
    if late_cycle and early_cycle and float(late_cycle.get("high_risk_event_rate") or 0.0) < float(
        early_cycle.get("high_risk_event_rate") or 0.0
    ):
        items.append(
            {
                "type": "late_cycle_not_risk_enriched",
                "severity": "medium",
                "evidence": {
                    "late_cycle_high_risk_event_rate": late_cycle.get("high_risk_event_rate"),
                    "early_cycle_high_risk_event_rate": early_cycle.get("high_risk_event_rate"),
                },
            }
        )
    for period in period_cases:
        if period.get("period") in {"2018_bear", "2022_bear"} and int(period.get("error_case_count") or 0) > 0:
            items.append(
                {
                    "type": "bear_period_phase_miss_cases",
                    "severity": "high",
                    "evidence": {
                        "period": period.get("period"),
                        "error_case_count": period.get("error_case_count"),
                    },
                }
            )
    return items


def build_phase_effectiveness_audit(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    market_phase = _read_json(root / "market_phase_snapshot.json")
    policy_effectiveness = _read_json(root / "policy_effectiveness.json")
    if not isinstance(market_phase, Mapping) or not market_phase.get("historical_replay"):
        raise RuntimeError("market_phase_snapshot.json is missing or incomplete.")
    if not isinstance(policy_effectiveness, Mapping) or not policy_effectiveness.get("validation_rows"):
        raise RuntimeError("policy_effectiveness.json is missing or incomplete.")

    joined = _joined_rows(market_phase, policy_effectiveness)
    phase_groups = _phase_group_summary(joined)
    phase_spread = _phase_spread(phase_groups)
    usefulness = _section(_section(policy_effectiveness, "summary"), "policy_usefulness")
    model_comparison = {
        "structural_high_risk_rate_spread": usefulness.get("structural_high_risk_rate_spread"),
        "opportunity_risk_high_risk_rate_spread": usefulness.get("opportunity_risk_high_risk_rate_spread"),
        "policy_high_risk_rate_spread": usefulness.get("policy_high_risk_rate_spread"),
        "phase_high_risk_rate_spread": phase_spread,
        "phase_vs_structural": (
            "underperform"
            if usefulness.get("structural_high_risk_rate_spread") is not None
            and phase_spread <= float(usefulness.get("structural_high_risk_rate_spread") or 0.0)
            else "outperform"
        ),
    }
    period_cases = [_period_error_cases(period, joined) for period in DEFAULT_PERIODS]
    transition = analyze_phase_transitions(market_phase.get("historical_replay") or [])
    review_items = _calibration_review_items(market_phase, phase_groups, model_comparison, period_cases)
    return {
        "metadata": {
            "engine": "V4.7 Market Phase Effectiveness Audit & Calibration Review",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _section(market_phase, "metadata").get("as_of"),
            "source_engine": _section(market_phase, "metadata").get("engine"),
            "purpose": "Audit fixed V4.6 phase usefulness, transitions, and misclassification cases without changing rules.",
        },
        "summary": {
            "usable_rows": len(joined),
            "model_comparison": model_comparison,
            "phase_group_summary": phase_groups,
            "review_item_count": len(review_items),
            "review_items": review_items,
            "key_read": _key_read(model_comparison, review_items),
        },
        "transition_analysis": transition,
        "period_error_cases": period_cases,
        "validation_rows": joined,
        "data_quality": {
            "uses_fixed_v4_6_phase": True,
            "uses_v4_5_future_labels_only_for_validation": True,
            "does_not_reclassify_phase": True,
            "no_threshold_tuning": True,
        },
        "constraints": {
            "audit_only": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization": True,
            "does_not_modify_v4_6_phase_rules": True,
        },
    }


def _key_read(model_comparison: Mapping[str, object], review_items: Sequence[Mapping[str, object]]) -> str:
    phase = model_comparison.get("phase_high_risk_rate_spread")
    structural = model_comparison.get("structural_high_risk_rate_spread")
    verdict = model_comparison.get("phase_vs_structural")
    return (
        f"Phase high-risk spread is {phase}, structural spread is {structural}; "
        f"phase_vs_structural={verdict}. Review items: {len(review_items)}."
    )


def write_phase_effectiveness_audit(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
