from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


DEFAULT_GATE_PATH = DATA_DIR / "research_candidate_promotion_gate.json"
DEFAULT_PHASE1_PATH = DATA_DIR / "allocation_experiment_phase1_validation.json"
DEFAULT_SCENARIO_AUDIT_PATH = DATA_DIR / "research_decision_scenario_audit.json"
DEFAULT_CONTRADICTION_PATH = DATA_DIR / "research_decision_contradiction.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "research_candidate_deep_validation.json"

TARGET_HYPOTHESES = {
    "H2": "risk_dominant_protection_persistence",
    "H4": "contradiction_first_promotion_gate",
}
ALLOWED_DEEP_STATUS = {"supported", "inconclusive", "unsupported"}
FORBIDDEN_OUTPUT_KEYS = {
    "asset_selection",
    "broker_order",
    "buy_signal",
    "etf_mapping",
    "exposure_percent",
    "optimization",
    "portfolio_weight",
    "rebalance_instruction",
    "sell_signal",
    "top_n",
    "trade_signal",
}


def _read_json(path: str | Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []


def _project_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys


def _by_id(rows: object, key: str) -> dict[str, Mapping[str, Any]]:
    return {str(_mapping(row).get(key)): _mapping(row) for row in _sequence(rows)}


def _status_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        status: sum(1 for row in rows if row.get("status") == status)
        for status in sorted(ALLOWED_DEEP_STATUS)
    }


def _h2_deep_result(
    gate_row: Mapping[str, Any],
    phase1_row: Mapping[str, Any],
    scenario_summary: Mapping[str, Any],
    contradiction_summary: Mapping[str, Any],
) -> dict[str, object]:
    consistency_counts = _mapping(scenario_summary.get("consistency_counts"))
    scenario_count = int(scenario_summary.get("scenario_count") or 0)
    low_count = int(consistency_counts.get("low") or 0)
    medium_count = int(consistency_counts.get("medium") or 0)
    low_consistency_share = round(low_count / scenario_count, 6) if scenario_count else None
    reason_counts = _mapping(contradiction_summary.get("possible_reason_counts"))
    risk_lag_cases = int(reason_counts.get("risk_axis_lag_or_structural_rotation_missed") or 0)
    contradiction_case_count = int(scenario_summary.get("contradiction_case_count") or 0)
    average_transition_rate = scenario_summary.get("average_transition_rate")

    strict_stability_pass = (
        gate_row.get("research_status") == "continue_research"
        and phase1_row.get("validation_status") == "supported"
        and low_consistency_share is not None
        and low_consistency_share <= 0.33
        and risk_lag_cases == 0
    )
    status = "supported" if strict_stability_pass else "inconclusive"
    return {
        "hypothesis_id": "H2",
        "hypothesis_name": TARGET_HYPOTHESES["H2"],
        "validation_depth": "extended",
        "status": status,
        "research_only": True,
        "source_gate_status": gate_row.get("research_status"),
        "phase1_status": phase1_row.get("validation_status"),
        "deep_checks": {
            "scenario_count": scenario_count,
            "low_consistency_count": low_count,
            "medium_consistency_count": medium_count,
            "low_consistency_share": low_consistency_share,
            "average_transition_rate": average_transition_rate,
            "contradiction_case_count": contradiction_case_count,
            "risk_axis_lag_or_structural_rotation_missed_count": risk_lag_cases,
            "strict_stability_pass": strict_stability_pass,
        },
        "evidence_read": [
            "v9_7_continue_research",
            "v9_6_supported",
            "v8_2_scenario_consistency_mixed",
            "v8_3_risk_axis_lag_case_present" if risk_lag_cases else "v8_3_no_risk_axis_lag_case",
        ],
        "limitations": [
            "risk_axis_visible_but_not_stable_enough_across_scenarios",
            "low_consistency_share_above_strict_threshold" if not strict_stability_pass else "strict_stability_threshold_passed",
        ],
        "next_research_step": "build_non_investable_risk_axis_stability_audit",
        "promotion_allowed": False,
        "strategy_promotion": False,
        "allocation_promotion": False,
        "investable_output": False,
        "boundary": "Research-only extended validation; do not convert to strategy, allocation, assets, ETFs, weights, optimization, or trades.",
    }


def _h4_deep_result(
    gate_row: Mapping[str, Any],
    phase1_row: Mapping[str, Any],
    gate_summary: Mapping[str, Any],
    contradiction_summary: Mapping[str, Any],
) -> dict[str, object]:
    focus_scenario_count = int(contradiction_summary.get("focus_scenario_count") or 0)
    attribution_count = int(contradiction_summary.get("attribution_count") or 0)
    contradiction_type_counts = _mapping(contradiction_summary.get("contradiction_type_counts"))
    type_count = len(contradiction_type_counts)
    frozen_count = int(gate_summary.get("freeze_count") or 0)
    promotion_blocked = (
        gate_summary.get("promotion_allowed") is False
        and gate_summary.get("strategy_promotion") is False
        and gate_summary.get("investable_output") is False
    )
    attribution_coverage_pass = focus_scenario_count > 0 and attribution_count >= focus_scenario_count and type_count >= 3
    status = (
        "supported"
        if gate_row.get("research_status") == "continue_research"
        and phase1_row.get("validation_status") == "supported"
        and attribution_coverage_pass
        and promotion_blocked
        else "inconclusive"
    )
    return {
        "hypothesis_id": "H4",
        "hypothesis_name": TARGET_HYPOTHESES["H4"],
        "validation_depth": "extended",
        "status": status,
        "research_only": True,
        "source_gate_status": gate_row.get("research_status"),
        "phase1_status": phase1_row.get("validation_status"),
        "deep_checks": {
            "focus_scenario_count": focus_scenario_count,
            "attribution_count": attribution_count,
            "contradiction_type_count": type_count,
            "frozen_hypothesis_count": frozen_count,
            "attribution_coverage_pass": attribution_coverage_pass,
            "promotion_blocked": promotion_blocked,
        },
        "evidence_read": [
            "v9_7_continue_research",
            "v9_6_supported",
            "v8_3_focus_scenarios_attributed",
            "v9_7_promotion_blocked",
        ],
        "limitations": [
            "supported_as_research_gate_discipline_only",
            "still_no_counterfactual_strategy_or_allocation_result",
        ],
        "next_research_step": "build_non_investable_contradiction_gate_effectiveness_audit",
        "promotion_allowed": False,
        "strategy_promotion": False,
        "allocation_promotion": False,
        "investable_output": False,
        "boundary": "Research-only extended validation; do not convert to strategy, allocation, assets, ETFs, weights, optimization, or trades.",
    }


def validate_research_candidate_deep_validation(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    constraints = _mapping(payload.get("constraints"))
    results = payload.get("deep_validation_results")
    if not isinstance(results, list) or len(results) != 2:
        raise AssertionError("deep_validation_results must contain H2 and H4 only")

    expected_ids = set(TARGET_HYPOTHESES)
    actual_ids = {str(_mapping(row).get("hypothesis_id")) for row in results}
    if actual_ids != expected_ids:
        raise AssertionError(f"unexpected hypothesis ids: {sorted(actual_ids)}")

    for key in (
        "promotion_allowed",
        "strategy_promotion",
        "allocation_promotion",
        "investable_output",
        "investable_output_generated",
        "ready_for_asset_selection",
        "ready_for_etf_mapping",
        "ready_for_weight_generation",
        "ready_for_optimization",
        "ready_for_trade",
    ):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    for row in results:
        item = _mapping(row)
        if item.get("status") not in ALLOWED_DEEP_STATUS:
            raise AssertionError(f"{item.get('hypothesis_id')} invalid status")
        if item.get("validation_depth") != "extended":
            raise AssertionError("validation_depth must be extended")
        if item.get("research_only") is not True:
            raise AssertionError("research_only must be true")
        for key in ("promotion_allowed", "strategy_promotion", "allocation_promotion", "investable_output"):
            if item.get(key) is not False:
                raise AssertionError(f"{item.get('hypothesis_id')}.{key} must be false")

    required_constraints = [
        "research_only",
        "deep_validation_only",
        "uses_frozen_artifacts_only",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_generate_portfolio_weight",
        "does_not_generate_allocation",
        "does_not_optimize_parameters",
        "does_not_generate_trade_signal",
        "no_order_generation",
        "no_broker_connection",
    ]
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(set(_walk_keys(payload)) - {"forbidden_outputs"})
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found outside forbidden_outputs: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_result_count": len(results),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_research_candidate_deep_validation(
    *,
    gate_path: str | Path = DEFAULT_GATE_PATH,
    phase1_path: str | Path = DEFAULT_PHASE1_PATH,
    scenario_audit_path: str | Path = DEFAULT_SCENARIO_AUDIT_PATH,
    contradiction_path: str | Path = DEFAULT_CONTRADICTION_PATH,
) -> dict[str, object]:
    gate = _read_json(gate_path)
    phase1 = _read_json(phase1_path)
    scenario = _read_json(scenario_audit_path)
    contradiction = _read_json(contradiction_path)
    if not all((gate, phase1, scenario, contradiction)):
        raise RuntimeError("V9.8 inputs missing; rebuild V9.7, V9.6, V8.2, and V8.3 artifacts.")

    gate_summary = _mapping(gate.get("summary"))
    scenario_summary = _mapping(scenario.get("summary"))
    contradiction_summary = _mapping(contradiction.get("summary"))
    gate_by_id = _by_id(gate.get("gate_results"), "hypothesis_id")
    phase1_by_id = _by_id(phase1.get("validation_results"), "experiment_id")
    missing = [hypothesis_id for hypothesis_id in TARGET_HYPOTHESES if hypothesis_id not in gate_by_id or hypothesis_id not in phase1_by_id]
    if missing:
        raise RuntimeError(f"V9.8 target hypotheses missing from inputs: {missing}")

    deep_results: list[Mapping[str, Any]] = [
        _h2_deep_result(gate_by_id["H2"], phase1_by_id["H2"], scenario_summary, contradiction_summary),
        _h4_deep_result(gate_by_id["H4"], phase1_by_id["H4"], gate_summary, contradiction_summary),
    ]
    counts = _status_counts(deep_results)
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V9.8 Research Candidate Deep Validation Framework",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(gate.get("metadata")).get("as_of"),
            "input_files": {
                "v9_7_research_candidate_gate": _project_path(gate_path),
                "v9_6_phase1_validation": _project_path(phase1_path),
                "v8_2_scenario_audit": _project_path(scenario_audit_path),
                "v8_3_contradiction_attribution": _project_path(contradiction_path),
            },
            "purpose": "Deepen validation for H2 and H4 continue_research hypotheses without producing strategy, allocation, asset, ETF, weight, optimization, or trade output.",
        },
        "summary": {
            "target_hypothesis_count": len(TARGET_HYPOTHESES),
            "validation_result_count": len(deep_results),
            "supported_count": counts.get("supported", 0),
            "inconclusive_count": counts.get("inconclusive", 0),
            "unsupported_count": counts.get("unsupported", 0),
            "promotion_allowed": False,
            "strategy_promotion": False,
            "allocation_promotion": False,
            "investable_output": False,
            "investable_output_generated": False,
            "ready_for_asset_selection": False,
            "ready_for_etf_mapping": False,
            "ready_for_weight_generation": False,
            "ready_for_optimization": False,
            "ready_for_trade": False,
            "conclusion": "research_candidate_deep_validation_completed_research_only_no_strategy",
            "key_read": "H4 is supported as a contradiction-first research gate discipline; H2 remains inconclusive under stricter cross-scenario stability checks.",
        },
        "source_layer_evidence": {
            "gate_summary": gate_summary,
            "phase1_summary": phase1.get("summary") or {},
            "scenario_audit_summary": scenario_summary,
            "contradiction_summary": contradiction_summary,
        },
        "deep_validation_results": deep_results,
        "time_safety": {
            "uses_frozen_artifacts_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_backtest": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "research_only": True,
            "deep_validation_only": True,
            "uses_frozen_artifacts_only": True,
            "does_not_select_assets": True,
            "does_not_map_etf": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_allocation": True,
            "does_not_optimize_parameters": True,
            "does_not_generate_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
        "forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }
    payload["audit"] = validate_research_candidate_deep_validation(payload)
    return payload


def write_research_candidate_deep_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
