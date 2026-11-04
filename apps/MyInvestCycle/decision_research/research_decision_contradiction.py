from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


DEFAULT_SCENARIO_AUDIT_PATH = DATA_DIR / "research_decision_scenario_audit.json"
DEFAULT_DECISION_CONTEXT_PATH = DATA_DIR / "research_decision_context.json"
DEFAULT_TWO_AXIS_PATH = DATA_DIR / "two_axis_context_validation.json"
DEFAULT_OPPORTUNITY_PATH = DATA_DIR / "opportunity_feature_attribution.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "research_decision_contradiction.json"


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


def _classify_contradiction(row: Mapping[str, Any]) -> tuple[str, str, str]:
    scenario = str(row.get("scenario") or "")
    dominant = row.get("dominant_context")
    consistency = row.get("consistency")
    transition_rate = row.get("transition_rate")
    contradiction_rate = row.get("contradiction_rate")
    transition_high = isinstance(transition_rate, (int, float)) and transition_rate >= 0.6
    contradiction_high = isinstance(contradiction_rate, (int, float)) and contradiction_rate >= 0.25

    if scenario == "2018_bear" and dominant == "PARTICIPATE":
        return (
            "participation_context_during_bear",
            "risk_axis_lag_or_structural_rotation_missed",
            "medium",
        )
    if scenario == "2015_bull_bear_transition" and transition_high:
        return (
            "rapid_context_switching",
            "macro_context_transition_noise",
            "medium",
        )
    if scenario == "2024_2026_structural_market":
        return (
            "structural_market_opportunity_not_captured",
            "opportunity_axis_weak_and_width_index_divergence",
            "low",
        )
    if scenario == "2021_core_asset_divergence" and dominant == "WAIT":
        return (
            "persistent_wait_during_style_divergence",
            "style_divergence_not_resolved_by_current_context",
            "low",
        )
    if contradiction_high:
        return (
            "high_contradiction_density",
            "context_label_conflict",
            "low",
        )
    if consistency == "low":
        return (
            "low_explanation_consistency",
            "scenario_context_not_stable",
            "low",
        )
    return (
        "monitor_only_no_primary_contradiction",
        "scenario_not_primary_failure_case",
        "low",
    )


def _scenario_rows(two_axis_rows: list[Mapping[str, Any]], scenario: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    start = str(scenario.get("start") or "")
    end = str(scenario.get("end") or "")
    return [row for row in two_axis_rows if start <= str(row.get("date") or "") <= end]


def _row_evidence(rows: list[Mapping[str, Any]]) -> dict[str, object]:
    decision_modes = Counter(str(row.get("v6_2_decision_mode") or "UNKNOWN") for row in rows)
    risk_states = Counter(str(row.get("risk_state") or "UNKNOWN") for row in rows)
    opportunity_states = Counter(str(row.get("opportunity_state") or "UNKNOWN") for row in rows)
    contradiction_examples = []
    for row in rows:
        contradictions = row.get("contradictions") or []
        if contradictions:
            contradiction_examples.append(
                {
                    "date": row.get("date"),
                    "two_axis_label": row.get("two_axis_label"),
                    "decision_mode": row.get("v6_2_decision_mode"),
                    "contradictions": contradictions,
                }
            )
        if len(contradiction_examples) >= 3:
            break
    return {
        "decision_mode_counts": dict(sorted(decision_modes.items())),
        "risk_state_counts": dict(sorted(risk_states.items())),
        "opportunity_state_counts": dict(sorted(opportunity_states.items())),
        "contradiction_examples": contradiction_examples,
    }


def _attribution_row(scenario: Mapping[str, Any], two_axis_rows: list[Mapping[str, Any]]) -> dict[str, object]:
    contradiction_type, possible_reason, confidence_level = _classify_contradiction(scenario)
    rows = _scenario_rows(two_axis_rows, scenario)
    return {
        "scenario": scenario.get("scenario"),
        "name": scenario.get("name"),
        "consistency": scenario.get("consistency"),
        "dominant_context": scenario.get("dominant_context"),
        "observation_count": scenario.get("observation_count"),
        "transition_rate": scenario.get("transition_rate"),
        "contradiction_count": scenario.get("contradiction_count"),
        "contradiction_rate": scenario.get("contradiction_rate"),
        "contradiction_type": contradiction_type,
        "possible_reason": possible_reason,
        "confidence_level": confidence_level,
        "evidence": {
            "dominant_context_share": scenario.get("dominant_context_share"),
            "market_phase_distribution": scenario.get("market_phase_distribution"),
            "two_axis_distribution": scenario.get("two_axis_distribution"),
            **_row_evidence(rows),
        },
        "research_only": True,
        "no_rule_change": True,
    }


def build_research_decision_contradiction(
    *,
    scenario_audit_path: str | Path = DEFAULT_SCENARIO_AUDIT_PATH,
    decision_context_path: str | Path = DEFAULT_DECISION_CONTEXT_PATH,
    two_axis_path: str | Path = DEFAULT_TWO_AXIS_PATH,
    opportunity_path: str | Path = DEFAULT_OPPORTUNITY_PATH,
) -> dict[str, object]:
    scenario_audit = _read_json(scenario_audit_path)
    decision_context = _read_json(decision_context_path)
    two_axis = _read_json(two_axis_path)
    opportunity = _read_json(opportunity_path)
    if not all((scenario_audit, decision_context, two_axis, opportunity)):
        raise RuntimeError("V8.3 inputs missing; run V8.1/V8.2 and frozen V6/V7 builders first.")

    scenario_rows = [
        _mapping(row)
        for row in scenario_audit.get("scenarios") or []
        if isinstance(row, Mapping)
    ]
    two_axis_rows = [
        _mapping(row)
        for row in two_axis.get("rows") or []
        if isinstance(row, Mapping)
    ]
    focus_rows = [
        row
        for row in scenario_rows
        if row.get("consistency") == "low"
        or int(row.get("contradiction_count") or 0) > 0
        or row.get("scenario") == "2024_2026_structural_market"
    ]
    attributions = [_attribution_row(row, two_axis_rows) for row in focus_rows]
    type_counts = Counter(str(row.get("contradiction_type") or "unknown") for row in attributions)
    reason_counts = Counter(str(row.get("possible_reason") or "unknown") for row in attributions)
    decision_summary = _mapping(decision_context.get("summary"))
    opportunity_summary = _mapping(opportunity.get("summary"))
    return {
        "metadata": {
            "engine": "V8.3 Research Decision Contradiction Attribution",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(two_axis.get("metadata")).get("as_of"),
            "input_files": {
                "scenario_audit": _project_path(scenario_audit_path),
                "research_decision_context": _project_path(decision_context_path),
                "two_axis_context": _project_path(two_axis_path),
                "opportunity_feature_attribution": _project_path(opportunity_path),
            },
            "purpose": "Attribute why V8.1 research context fails in selected historical scenarios; no rule changes, score, rank, allocation, or trade output.",
        },
        "summary": {
            "base_decision_context": decision_summary.get("decision_context"),
            "base_research_posture": decision_summary.get("research_posture"),
            "scenario_count": len(scenario_rows),
            "focus_scenario_count": len(focus_rows),
            "attribution_count": len(attributions),
            "contradiction_type_counts": dict(sorted(type_counts.items())),
            "possible_reason_counts": dict(sorted(reason_counts.items())),
            "opportunity_context_status": opportunity_summary.get("conclusion"),
            "ready_for_scoring": False,
            "ready_for_ranking": False,
            "ready_for_allocation": False,
            "ready_for_trade": False,
            "conclusion": "contradiction_attribution_research_only_no_rule_change",
            "key_read": "V8.3 explains failure modes in low-consistency scenarios but does not change models, states, thresholds, allocations, or trades.",
        },
        "attributions": attributions,
        "focus_policy": {
            "included_when_consistency_low": True,
            "included_when_contradiction_count_positive": True,
            "always_include_structural_market": True,
            "primary_focus_scenarios": [row.get("scenario") for row in focus_rows],
        },
        "time_safety": {
            "uses_existing_v8_2_output_only": True,
            "uses_existing_v8_1_output_only": True,
            "uses_existing_v6_rows_only": True,
            "uses_existing_v7_attribution_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
        },
        "data_quality": {
            "fixed_attribution_rules": True,
            "no_new_state": True,
            "no_new_feature_search": True,
            "no_scoring": True,
            "no_ranking": True,
            "no_top_n": True,
            "no_allocation": True,
            "no_backtest": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "attribution_only": True,
            "research_only": True,
            "does_not_modify_v6": True,
            "does_not_modify_v7": True,
            "does_not_add_state": True,
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
            "no_parameter_optimization": True,
        },
    }


def write_research_decision_contradiction(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
