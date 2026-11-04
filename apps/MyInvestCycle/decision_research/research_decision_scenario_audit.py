from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


DEFAULT_DECISION_CONTEXT_PATH = DATA_DIR / "research_decision_context.json"
DEFAULT_TWO_AXIS_PATH = DATA_DIR / "two_axis_context_validation.json"
DEFAULT_INFORMATION_PATH = DATA_DIR / "context_information_attribution.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "research_decision_scenario_audit.json"

SCENARIOS = [
    {
        "scenario": "2015_bull_bear_transition",
        "name": "2015 牛熊转换",
        "start": "20150101",
        "end": "20160229",
    },
    {
        "scenario": "2018_bear",
        "name": "2018 熊市",
        "start": "20180101",
        "end": "20181231",
    },
    {
        "scenario": "2020_recovery",
        "name": "2020 恢复",
        "start": "20200101",
        "end": "20201231",
    },
    {
        "scenario": "2021_core_asset_divergence",
        "name": "2021 核心资产分化",
        "start": "20210101",
        "end": "20211231",
    },
    {
        "scenario": "2022_bear",
        "name": "2022 熊市",
        "start": "20220101",
        "end": "20221231",
    },
    {
        "scenario": "2024_2026_structural_market",
        "name": "2024-2026 结构行情",
        "start": "20240101",
        "end": "20260707",
    },
]


def _read_json(path: str | Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _project_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _distribution(rows: list[Mapping[str, Any]], key: str) -> dict[str, dict[str, object]]:
    counts = Counter(str(row.get(key) or "UNKNOWN") for row in rows)
    total = len(rows)
    return {
        label: {"count": count, "share": round(count / total, 6) if total else 0.0}
        for label, count in sorted(counts.items())
    }


def _dominant(distribution: Mapping[str, Mapping[str, object]]) -> tuple[str | None, float]:
    if not distribution:
        return None, 0.0
    label, item = max(distribution.items(), key=lambda pair: int(pair[1].get("count") or 0))
    share = item.get("share")
    return label, float(share) if isinstance(share, (int, float)) else 0.0


def _transition_rate(rows: list[Mapping[str, Any]], key: str) -> tuple[int, float | None]:
    ordered = sorted(rows, key=lambda row: str(row.get("date") or ""))
    transitions = 0
    previous = None
    for row in ordered:
        current = row.get(key)
        if previous is not None and current != previous:
            transitions += 1
        previous = current
    denominator = max(len(ordered) - 1, 0)
    return transitions, round(transitions / denominator, 6) if denominator else None


def _missing_context_count(rows: list[Mapping[str, Any]]) -> int:
    missing = 0
    for row in rows:
        quality = _mapping(row.get("data_quality"))
        risk_count = quality.get("risk_component_count")
        opportunity_count = quality.get("opportunity_component_count")
        if not isinstance(risk_count, int) or not isinstance(opportunity_count, int):
            missing += 1
        elif risk_count < 3 or opportunity_count < 3:
            missing += 1
    return missing


def _consistency_label(
    *,
    observation_count: int,
    dominant_share: float,
    transition_rate: float | None,
    contradiction_rate: float,
    missing_context_rate: float,
) -> str:
    if observation_count < 3:
        return "insufficient"
    stable_transition = transition_rate is not None and transition_rate <= 0.35
    if dominant_share >= 0.6 and stable_transition and contradiction_rate <= 0.15 and missing_context_rate <= 0.25:
        return "high"
    if dominant_share >= 0.4 and contradiction_rate <= 0.25 and missing_context_rate <= 0.4:
        return "medium"
    return "low"


def _interpretation(label: str | None) -> str:
    if label == "AVOID":
        return "risk_pressure_visible"
    if label == "PROTECT_BUT_PARTICIPATE":
        return "protection_pressure_with_participation"
    if label == "PARTICIPATE":
        return "participation_context_visible"
    if label == "WAIT":
        return "wait_or_mixed_context"
    return "coverage_missing"


def _scenario_row(scenario: Mapping[str, str], rows: list[Mapping[str, Any]]) -> dict[str, object]:
    start = scenario["start"]
    end = scenario["end"]
    scoped = [row for row in rows if start <= str(row.get("date") or "") <= end]
    two_axis_distribution = _distribution(scoped, "two_axis_label")
    market_phase_distribution = _distribution(scoped, "market_phase")
    risk_state_distribution = _distribution(scoped, "risk_state")
    opportunity_state_distribution = _distribution(scoped, "opportunity_state")
    dominant_label, dominant_share = _dominant(two_axis_distribution)
    transitions, transition_rate = _transition_rate(scoped, "two_axis_label")
    contradiction_count = sum(len(row.get("contradictions") or []) for row in scoped)
    missing_context_count = _missing_context_count(scoped)
    observation_count = len(scoped)
    contradiction_rate = round(contradiction_count / observation_count, 6) if observation_count else 0.0
    missing_context_rate = round(missing_context_count / observation_count, 6) if observation_count else 1.0
    consistency = _consistency_label(
        observation_count=observation_count,
        dominant_share=dominant_share,
        transition_rate=transition_rate,
        contradiction_rate=contradiction_rate,
        missing_context_rate=missing_context_rate,
    )
    return {
        "scenario": scenario["scenario"],
        "name": scenario["name"],
        "start": start,
        "end": end,
        "observation_count": observation_count,
        "coverage_status": "covered" if observation_count >= 3 else "insufficient",
        "dominant_context": dominant_label,
        "dominant_context_share": dominant_share,
        "interpretation": _interpretation(dominant_label),
        "consistency": consistency,
        "transition_count": transitions,
        "transition_rate": transition_rate,
        "contradiction_count": contradiction_count,
        "contradiction_rate": contradiction_rate,
        "missing_context_count": missing_context_count,
        "missing_context_rate": missing_context_rate,
        "two_axis_distribution": two_axis_distribution,
        "market_phase_distribution": market_phase_distribution,
        "risk_state_distribution": risk_state_distribution,
        "opportunity_state_distribution": opportunity_state_distribution,
        "research_only": True,
    }


def build_research_decision_scenario_audit(
    *,
    decision_context_path: str | Path = DEFAULT_DECISION_CONTEXT_PATH,
    two_axis_path: str | Path = DEFAULT_TWO_AXIS_PATH,
    information_path: str | Path = DEFAULT_INFORMATION_PATH,
) -> dict[str, object]:
    decision_context = _read_json(decision_context_path)
    two_axis = _read_json(two_axis_path)
    information = _read_json(information_path)
    if not all((decision_context, two_axis, information)):
        raise RuntimeError("V8.2 inputs missing; run scripts/run_research_decision_context.py and V6 context builders first.")

    two_axis_rows = [
        _mapping(row)
        for row in two_axis.get("rows") or []
        if isinstance(row, Mapping)
    ]
    information_rows = [
        _mapping(row)
        for row in information.get("rows") or []
        if isinstance(row, Mapping)
    ]
    scenarios = [_scenario_row(item, two_axis_rows) for item in SCENARIOS]
    consistency_counts = Counter(str(row.get("consistency") or "unknown") for row in scenarios)
    dominant_counts = Counter(str(row.get("dominant_context") or "UNKNOWN") for row in scenarios)
    covered = [row for row in scenarios if row["coverage_status"] == "covered"]
    transition_rates = [
        row["transition_rate"]
        for row in scenarios
        if isinstance(row.get("transition_rate"), (int, float))
    ]
    contradiction_total = sum(int(row.get("contradiction_count") or 0) for row in scenarios)
    missing_total = sum(int(row.get("missing_context_count") or 0) for row in scenarios)
    decision_summary = _mapping(decision_context.get("summary"))
    return {
        "metadata": {
            "engine": "V8.2 Research Decision Historical Scenario Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(two_axis.get("metadata")).get("as_of"),
            "input_files": {
                "research_decision_context": _project_path(decision_context_path),
                "two_axis_context": _project_path(two_axis_path),
                "context_information_attribution": _project_path(information_path),
            },
            "purpose": "Audit whether the V8.1 research context explains historical scenarios consistently; no returns, score, rank, allocation, or trade output.",
        },
        "summary": {
            "base_decision_context": decision_summary.get("decision_context"),
            "base_research_posture": decision_summary.get("research_posture"),
            "scenario_count": len(scenarios),
            "covered_scenario_count": len(covered),
            "consistency_counts": dict(sorted(consistency_counts.items())),
            "dominant_context_counts": dict(sorted(dominant_counts.items())),
            "average_transition_rate": round(sum(transition_rates) / len(transition_rates), 6) if transition_rates else None,
            "contradiction_case_count": contradiction_total,
            "missing_context_case_count": missing_total,
            "ready_for_scoring": False,
            "ready_for_ranking": False,
            "ready_for_allocation": False,
            "ready_for_trade": False,
            "conclusion": "scenario_explanation_audit_only_no_strategy",
            "key_read": "V8.2 checks historical explanation consistency only; it does not use returns, produce rankings, allocate assets, or trade.",
        },
        "scenarios": scenarios,
        "coverage": {
            "two_axis_row_count": len(two_axis_rows),
            "information_row_count": len(information_rows),
            "scenario_definitions": SCENARIOS,
        },
        "time_safety": {
            "uses_existing_v8_1_output_only": True,
            "uses_existing_v6_rows_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_use_return_metrics": True,
        },
        "data_quality": {
            "fixed_scenarios": True,
            "no_new_feature_search": True,
            "no_scoring": True,
            "no_ranking": True,
            "no_top_n": True,
            "no_allocation": True,
            "no_backtest": True,
            "no_return_metric": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "audit_only": True,
            "research_only": True,
            "does_not_create_opportunity_score": True,
            "does_not_rank_assets": True,
            "does_not_select_top_assets": True,
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


def write_research_decision_scenario_audit(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
