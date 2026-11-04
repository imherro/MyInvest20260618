from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


DEFAULT_ARCHITECTURE_PATH = DATA_DIR / "allocation_research_architecture.json"
DEFAULT_HYPOTHESES_PATH = DATA_DIR / "allocation_research_hypotheses.json"
DEFAULT_VALIDATION_PLAN_PATH = DATA_DIR / "allocation_validation_plan.json"
DEFAULT_EXPERIMENT_TEMPLATES_PATH = DATA_DIR / "allocation_experiment_templates.json"
DEFAULT_PHASE0_PATH = DATA_DIR / "allocation_experiment_results_phase0.json"
DEFAULT_PHASE1_PATH = DATA_DIR / "allocation_experiment_phase1_validation.json"
DEFAULT_GATE_PATH = DATA_DIR / "research_candidate_promotion_gate.json"
DEFAULT_DEEP_VALIDATION_PATH = DATA_DIR / "research_candidate_deep_validation.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_research_evidence_freeze.json"

EXPECTED_HYPOTHESIS_STATUS = {
    "H1": "freeze",
    "H2": "inconclusive",
    "H3": "freeze",
    "H4": "supported_research_only",
}
FORBIDDEN_OUTPUT_KEYS = {
    "asset_selection",
    "backtest_result",
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


def _hypothesis_names(hypotheses: Mapping[str, object]) -> dict[str, str]:
    return {
        str(row.get("id")): str(row.get("name") or row.get("id"))
        for row in (_mapping(item) for item in _sequence(hypotheses.get("hypotheses")))
    }


def _build_hypothesis_status(
    *,
    hypotheses: Mapping[str, object],
    phase1: Mapping[str, object],
    gate: Mapping[str, object],
    deep_validation: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    names = _hypothesis_names(hypotheses)
    phase1_by_id = _by_id(phase1.get("validation_results"), "experiment_id")
    gate_by_id = _by_id(gate.get("gate_results"), "hypothesis_id")
    deep_by_id = _by_id(deep_validation.get("deep_validation_results"), "hypothesis_id")
    rows: dict[str, dict[str, object]] = {}
    for hypothesis_id, final_status in EXPECTED_HYPOTHESIS_STATUS.items():
        phase1_row = phase1_by_id.get(hypothesis_id, {})
        gate_row = gate_by_id.get(hypothesis_id, {})
        deep_row = deep_by_id.get(hypothesis_id, {})
        if hypothesis_id == "H2":
            action = "retain_research_direction"
            direction = "risk_protection_research"
            reason = "V9.8 keeps H2 inconclusive under stricter scenario stability, so it may continue only as non-investable research evidence."
        elif hypothesis_id == "H4":
            action = "retain_research_direction"
            direction = "contradiction_gate_research"
            reason = "V9.8 supports H4 only as a contradiction-first research gate discipline, not as an investable rule."
        elif hypothesis_id == "H1":
            action = "pause_research_direction"
            direction = "risk_relief_opportunity_readiness"
            reason = "V9.7 freezes H1 because Phase 1 evidence remains inconclusive."
        else:
            action = "pause_research_direction"
            direction = "structural_opportunity_confirmation"
            reason = "V9.7 freezes H3 because structural opportunity capture is still an unresolved research gap."
        rows[hypothesis_id] = {
            "hypothesis_id": hypothesis_id,
            "hypothesis_name": names.get(hypothesis_id, hypothesis_id),
            "status": final_status,
            "decision_boundary": action,
            "research_direction": direction,
            "phase1_status": phase1_row.get("validation_status"),
            "gate_status": gate_row.get("research_status"),
            "deep_validation_status": deep_row.get("status") if deep_row else None,
            "evidence_reason": reason,
            "allowed_next_step": "research_evidence_review_only",
            "promotion_allowed": False,
            "strategy_promotion": False,
            "allocation_ready": False,
            "investable_output": False,
        }
    return rows


def validate_allocation_research_evidence_freeze(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    hypothesis_status = _mapping(payload.get("hypothesis_status"))
    constraints = _mapping(payload.get("constraints"))
    if summary.get("research_state") != "frozen":
        raise AssertionError("summary.research_state must be frozen")
    if set(hypothesis_status.keys()) != set(EXPECTED_HYPOTHESIS_STATUS):
        raise AssertionError("hypothesis_status must contain H1-H4")
    for hypothesis_id, expected_status in EXPECTED_HYPOTHESIS_STATUS.items():
        row = _mapping(hypothesis_status.get(hypothesis_id))
        if row.get("status") != expected_status:
            raise AssertionError(f"{hypothesis_id} status must be {expected_status}")
        for key in ("promotion_allowed", "strategy_promotion", "allocation_ready", "investable_output"):
            if row.get(key) is not False:
                raise AssertionError(f"{hypothesis_id}.{key} must be false")

    for key in (
        "promotion_allowed",
        "strategy_promotion",
        "allocation_ready",
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

    required_constraints = [
        "research_only",
        "evidence_freeze_only",
        "uses_v9_1_to_v9_8_artifacts_only",
        "does_not_add_state_layer",
        "does_not_add_hypothesis",
        "does_not_add_explanation_layer",
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
        "checked_hypothesis_count": len(hypothesis_status),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_allocation_research_evidence_freeze(
    *,
    architecture_path: str | Path = DEFAULT_ARCHITECTURE_PATH,
    hypotheses_path: str | Path = DEFAULT_HYPOTHESES_PATH,
    validation_plan_path: str | Path = DEFAULT_VALIDATION_PLAN_PATH,
    experiment_templates_path: str | Path = DEFAULT_EXPERIMENT_TEMPLATES_PATH,
    phase0_path: str | Path = DEFAULT_PHASE0_PATH,
    phase1_path: str | Path = DEFAULT_PHASE1_PATH,
    gate_path: str | Path = DEFAULT_GATE_PATH,
    deep_validation_path: str | Path = DEFAULT_DEEP_VALIDATION_PATH,
) -> dict[str, object]:
    architecture = _read_json(architecture_path)
    hypotheses = _read_json(hypotheses_path)
    validation_plan = _read_json(validation_plan_path)
    templates = _read_json(experiment_templates_path)
    phase0 = _read_json(phase0_path)
    phase1 = _read_json(phase1_path)
    gate = _read_json(gate_path)
    deep_validation = _read_json(deep_validation_path)
    inputs = [architecture, hypotheses, validation_plan, templates, phase0, phase1, gate, deep_validation]
    if not all(inputs):
        raise RuntimeError("V9.9 inputs missing; rebuild V9.1-V9.8 artifacts first.")

    hypothesis_status = _build_hypothesis_status(
        hypotheses=hypotheses,
        phase1=phase1,
        gate=gate,
        deep_validation=deep_validation,
    )
    retained = [
        hypothesis_id
        for hypothesis_id, row in hypothesis_status.items()
        if row["decision_boundary"] == "retain_research_direction"
    ]
    paused = [
        hypothesis_id
        for hypothesis_id, row in hypothesis_status.items()
        if row["decision_boundary"] == "pause_research_direction"
    ]
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V9.9 Allocation Research Evidence Freeze & Decision Boundary Summary",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(deep_validation.get("metadata")).get("as_of"),
            "input_files": {
                "v9_1_architecture": _project_path(architecture_path),
                "v9_2_hypotheses": _project_path(hypotheses_path),
                "v9_3_validation_plan": _project_path(validation_plan_path),
                "v9_4_experiment_templates": _project_path(experiment_templates_path),
                "v9_5_phase0_results": _project_path(phase0_path),
                "v9_6_phase1_validation": _project_path(phase1_path),
                "v9_7_research_candidate_gate": _project_path(gate_path),
                "v9_8_deep_validation": _project_path(deep_validation_path),
            },
            "purpose": "Freeze V9.1-V9.8 allocation research evidence and decision boundaries without entering strategy, allocation, optimization, or trading.",
        },
        "summary": {
            "research_state": "frozen",
            "evidence_scope": "V9.1-V9.8",
            "hypothesis_count": len(hypothesis_status),
            "retained_research_direction_count": len(retained),
            "paused_research_direction_count": len(paused),
            "supported_research_only_count": sum(1 for row in hypothesis_status.values() if row["status"] == "supported_research_only"),
            "inconclusive_research_count": sum(1 for row in hypothesis_status.values() if row["status"] == "inconclusive"),
            "promotion_allowed": False,
            "strategy_promotion": False,
            "allocation_ready": False,
            "investable_output": False,
            "investable_output_generated": False,
            "ready_for_asset_selection": False,
            "ready_for_etf_mapping": False,
            "ready_for_weight_generation": False,
            "ready_for_optimization": False,
            "ready_for_trade": False,
            "conclusion": "allocation_research_evidence_frozen_no_strategy_no_allocation",
            "key_read": "V9 evidence is frozen: H2 and H4 remain research directions only; H1 and H3 are paused; no allocation, strategy, optimization, or trade output is ready.",
        },
        "hypothesis_status": hypothesis_status,
        "decision_boundary_summary": {
            "retained_research_directions": retained,
            "paused_research_directions": paused,
            "allowed_next_actions": [
                "read_existing_evidence",
                "audit_existing_evidence_consistency",
                "prepare_external_review_package",
            ],
            "prohibited_next_actions": [
                "do_not_add_new_state_layer",
                "do_not_add_new_hypothesis",
                "do_not_add_new_explanation_layer",
                "do_not_generate_strategy",
                "do_not_generate_allocation",
                "do_not_map_assets_or_etfs",
                "do_not_generate_weights_or_trades",
            ],
        },
        "source_layer_evidence": {
            "v9_1_summary": architecture.get("summary") or {},
            "v9_2_summary": hypotheses.get("summary") or {},
            "v9_3_summary": validation_plan.get("summary") or {},
            "v9_4_summary": templates.get("summary") or {},
            "v9_5_summary": phase0.get("summary") or {},
            "v9_6_summary": phase1.get("summary") or {},
            "v9_7_summary": gate.get("summary") or {},
            "v9_8_summary": deep_validation.get("summary") or {},
        },
        "time_safety": {
            "uses_v9_1_to_v9_8_artifacts_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_backtest": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "research_only": True,
            "evidence_freeze_only": True,
            "uses_v9_1_to_v9_8_artifacts_only": True,
            "does_not_add_state_layer": True,
            "does_not_add_hypothesis": True,
            "does_not_add_explanation_layer": True,
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
    payload["audit"] = validate_allocation_research_evidence_freeze(payload)
    return payload


def write_allocation_research_evidence_freeze(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
