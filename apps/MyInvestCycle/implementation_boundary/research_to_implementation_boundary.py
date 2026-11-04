from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RESEARCH_PHASE_CLOSURE_PATH = DATA_DIR / "research_phase_closure.json"
DEFAULT_V10_BOUNDARY_PATH = DATA_DIR / "allocation_research_final_boundary.json"
DEFAULT_V11_H2_FREEZE_PATH = DATA_DIR / "h2_external_validation_result_freeze.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "research_to_implementation_boundary.json"

FORBIDDEN_OUTPUT_KEYS = {
    "asset_selection",
    "broker_order",
    "buy_signal",
    "etf_mapping",
    "exposure_percent",
    "optimization_result",
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


def _file_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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


def _component(
    *,
    component_id: str,
    source_status: str,
    boundary_status: str,
    candidate_role: str,
    implementation_allowed: bool,
    allowed_current_outputs: Sequence[str],
    required_before_implementation: Sequence[str],
    isolation_reason: str,
) -> dict[str, object]:
    return {
        "component_id": component_id,
        "source_status": source_status,
        "boundary_status": boundary_status,
        "candidate_role": candidate_role,
        "implementation_allowed": implementation_allowed,
        "allowed_current_outputs": list(allowed_current_outputs),
        "required_before_implementation": list(required_before_implementation),
        "isolation_reason": isolation_reason,
    }


def validate_research_to_implementation_boundary(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    constraints = _mapping(payload.get("constraints"))
    gate = _mapping(payload.get("implementation_entry_gate"))
    components = _sequence(payload.get("component_boundaries"))

    if summary.get("boundary_status") != "defined":
        raise AssertionError("summary.boundary_status must be defined")
    if summary.get("implementation_phase") != "not_started":
        raise AssertionError("implementation phase must remain not_started")
    if summary.get("research_phase_status") != "closed":
        raise AssertionError("research phase status must be closed")
    if summary.get("global_implementation_allowed") is not False:
        raise AssertionError("global implementation must remain blocked")
    if summary.get("investable_output") is not False:
        raise AssertionError("investable output must remain false")
    if summary.get("trade_ready") is not False:
        raise AssertionError("trade_ready must remain false")
    if summary.get("conclusion") != "research_to_implementation_boundary_defined_no_strategy_no_allocation":
        raise AssertionError("unexpected conclusion")

    if gate.get("current_gate_result") != "blocked":
        raise AssertionError("implementation entry gate must be blocked")
    if gate.get("requires_new_evidence_before_any_implementation") is not True:
        raise AssertionError("entry gate must require new evidence")

    if not components:
        raise AssertionError("component boundaries are required")
    candidate_components = [
        item
        for item in components
        if isinstance(item, Mapping) and item.get("boundary_status") in {"observation_only", "research_governance_only"}
    ]
    blocked_components = [
        item
        for item in components
        if isinstance(item, Mapping) and item.get("boundary_status") in {"isolated_not_ready", "disabled", "not_ready"}
    ]
    if len(candidate_components) != summary.get("implementation_candidate_count"):
        raise AssertionError("candidate count mismatch")
    if len(blocked_components) != summary.get("isolated_or_blocked_count"):
        raise AssertionError("blocked count mismatch")
    for item in components:
        if not isinstance(item, Mapping):
            raise AssertionError("component boundary must be mapping")
        if item.get("implementation_allowed") is not False:
            raise AssertionError(f"{item.get('component_id')} must not allow implementation")
        required = _sequence(item.get("required_before_implementation"))
        if not required:
            raise AssertionError(f"{item.get('component_id')} missing required evidence")

    required_constraints = [
        "boundary_design_only",
        "does_not_generate_strategy",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_generate_portfolio_weight",
        "does_not_generate_allocation",
        "does_not_optimize_parameters",
        "does_not_generate_trade_signal",
        "no_order_generation",
        "no_broker_connection",
        "requires_future_v12_evidence_before_implementation",
    ]
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")

    allowed_key_containers = {"forbidden_outputs"}
    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(
        key for key in _walk_keys(payload) if key not in allowed_key_containers
    )
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_boundary_status": summary.get("boundary_status"),
        "checked_gate_result": gate.get("current_gate_result"),
        "checked_component_count": len(components),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_research_to_implementation_boundary(
    *,
    research_phase_closure_path: str | Path = DEFAULT_RESEARCH_PHASE_CLOSURE_PATH,
    v10_boundary_path: str | Path = DEFAULT_V10_BOUNDARY_PATH,
    v11_h2_freeze_path: str | Path = DEFAULT_V11_H2_FREEZE_PATH,
) -> dict[str, object]:
    research_phase_closure = _read_json(research_phase_closure_path)
    v10_boundary = _read_json(v10_boundary_path)
    v11_h2 = _read_json(v11_h2_freeze_path)
    if not all((research_phase_closure, v10_boundary, v11_h2)):
        raise RuntimeError("V12.1 inputs missing; rebuild V10.3, V11.3 and V11.4 artifacts first.")

    phase_summary = _mapping(research_phase_closure.get("summary"))
    h2_summary = _mapping(v11_h2.get("summary"))
    h2_final = _mapping(v11_h2.get("final_conclusion"))
    input_paths = {
        "research_phase_closure": research_phase_closure_path,
        "allocation_research_final_boundary": v10_boundary_path,
        "h2_external_validation_result_freeze": v11_h2_freeze_path,
    }

    shared_required = [
        "independent_out_of_sample_validation",
        "pre_registered_decision_policy",
        "live_shadow_observation_period",
        "failure_and_rollback_criteria",
        "manual_review_before_any_investable_use",
    ]
    component_boundaries = [
        _component(
            component_id="risk_diagnostic_layer",
            source_status=str(phase_summary.get("risk_research_status") or "unknown"),
            boundary_status="observation_only",
            candidate_role="read_only_monitoring_context",
            implementation_allowed=False,
            allowed_current_outputs=["dashboard_label", "audit_context", "manual_observation_note"],
            required_before_implementation=[
                "stable_risk_warning_effect_across_holdout_windows",
                "false_warning_cost_bound",
                *shared_required,
            ],
            isolation_reason="Risk evidence is visible but has not passed a promotion gate for allocation or execution.",
        ),
        _component(
            component_id="protection_research_value",
            source_status=str(phase_summary.get("protection_research_status") or "unknown"),
            boundary_status="observation_only",
            candidate_role="risk_protection_research_context",
            implementation_allowed=False,
            allowed_current_outputs=["protection_evidence_summary", "audit_context"],
            required_before_implementation=[
                "cross_regime_drawdown_reduction_validation",
                "opportunity_cost_measurement",
                *shared_required,
            ],
            isolation_reason="Protection value is supported only as research evidence and cannot become an allocation action.",
        ),
        _component(
            component_id="contradiction_governance_layer",
            source_status=str(phase_summary.get("contradiction_governance_status") or "unknown"),
            boundary_status="research_governance_only",
            candidate_role="research_quality_gate",
            implementation_allowed=False,
            allowed_current_outputs=["contradiction_note", "research_review_gate"],
            required_before_implementation=[
                "governance_rule_stability_review",
                "independent_human_audit",
                *shared_required,
            ],
            isolation_reason="Contradiction governance can organize research review but cannot score assets or trigger trades.",
        ),
        _component(
            component_id="opportunity_prediction_layer",
            source_status=str(phase_summary.get("opportunity_research_status") or "unknown"),
            boundary_status="isolated_not_ready",
            candidate_role="none",
            implementation_allowed=False,
            allowed_current_outputs=["research_archive_reference"],
            required_before_implementation=[
                "positive_out_of_sample_information_coefficient",
                "feature_stability_across_market_structures",
                "tradable_proxy_confirmation",
                *shared_required,
            ],
            isolation_reason="Opportunity prediction has not shown enough stable forward value for implementation design.",
        ),
        _component(
            component_id="allocation_alpha_layer",
            source_status=str(phase_summary.get("allocation_status") or "unknown"),
            boundary_status="isolated_not_ready",
            candidate_role="none",
            implementation_allowed=False,
            allowed_current_outputs=["research_archive_reference"],
            required_before_implementation=[
                "positive_incremental_alpha_after_cost",
                "robustness_across_research_windows",
                "sample_split_validation",
                *shared_required,
            ],
            isolation_reason="Allocation alpha is not verified and must stay outside implementation.",
        ),
        _component(
            component_id="asset_selection_layer",
            source_status=str(phase_summary.get("asset_selection_status") or "unknown"),
            boundary_status="disabled",
            candidate_role="none",
            implementation_allowed=False,
            allowed_current_outputs=["not_available"],
            required_before_implementation=[
                "separate_asset_universe_research",
                "liquidity_and_tracking_error_audit",
                "survivorship_bias_audit",
                *shared_required,
            ],
            isolation_reason="No asset selection research has passed a gate; this layer is disabled.",
        ),
        _component(
            component_id="portfolio_construction_layer",
            source_status=str(phase_summary.get("portfolio_construction_status") or "unknown"),
            boundary_status="not_ready",
            candidate_role="none",
            implementation_allowed=False,
            allowed_current_outputs=["not_available"],
            required_before_implementation=[
                "risk_budget_policy_pre_registration",
                "turnover_and_cost_model",
                "stress_test_and_capacity_review",
                *shared_required,
            ],
            isolation_reason="Portfolio construction is not designed and cannot be inferred from research diagnostics.",
        ),
        _component(
            component_id="execution_layer",
            source_status=str(phase_summary.get("trading_status") or "unknown"),
            boundary_status="disabled",
            candidate_role="none",
            implementation_allowed=False,
            allowed_current_outputs=["not_available"],
            required_before_implementation=[
                "paper_trading_only_sandbox",
                "explicit_user_authorization",
                "broker_write_path_security_review",
                *shared_required,
            ],
            isolation_reason="Execution remains disabled; no broker, order or trade path is allowed.",
        ),
    ]
    candidate_count = sum(
        1
        for item in component_boundaries
        if item["boundary_status"] in {"observation_only", "research_governance_only"}
    )
    blocked_count = len(component_boundaries) - candidate_count

    payload: dict[str, object] = {
        "metadata": {
            "engine": "V12.1 Research-to-Implementation Boundary Design",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(research_phase_closure.get("metadata")).get("as_of"),
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Define the boundary between frozen research results and any future implementation design without creating a strategy, allocation, asset selection, portfolio construction, or trading output.",
        },
        "summary": {
            "boundary_status": "defined",
            "implementation_phase": "not_started",
            "research_phase_status": phase_summary.get("research_phase"),
            "implementation_candidate_count": candidate_count,
            "isolated_or_blocked_count": blocked_count,
            "global_implementation_allowed": False,
            "investable_output": False,
            "trade_ready": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "component_count": len(component_boundaries),
            "conclusion": "research_to_implementation_boundary_defined_no_strategy_no_allocation",
            "key_read": "Only read-only risk diagnostics and research-governance context can be carried forward as observation candidates; opportunity, allocation, asset selection, portfolio construction and execution remain isolated.",
        },
        "component_boundaries": component_boundaries,
        "implementation_entry_gate": {
            "current_gate_result": "blocked",
            "requires_new_evidence_before_any_implementation": True,
            "minimum_global_requirements": [
                "separate_v12_implementation_design_review",
                "independent_out_of_sample_validation",
                "pre_registered_decision_policy",
                "cost_turnover_capacity_review",
                "live_shadow_observation_period",
                "human_approval_before_promotion",
            ],
            "blocked_reasons": [
                "research architecture is closed but not investable",
                "H2 external validation is inconclusive",
                "opportunity and allocation research are not ready",
                "no asset, portfolio or execution layer is validated",
            ],
        },
        "permitted_current_outputs": [
            "read_only_dashboard",
            "research_audit_package",
            "observation_status_label",
            "manual_research_review_context",
        ],
        "explicitly_isolated_from_implementation": [
            "opportunity_prediction",
            "allocation_alpha",
            "asset_universe_selection",
            "portfolio_construction",
            "automatic_allocation",
            "execution_or_order_routing",
        ],
        "source_layer_evidence": {
            "research_phase_closure": {
                "research_phase": phase_summary.get("research_phase"),
                "project_completion_status": phase_summary.get("project_completion_status"),
                "investable_output": phase_summary.get("investable_output"),
            },
            "v10_final_boundary": {
                "summary": _mapping(v10_boundary.get("summary")),
            },
            "v11_h2_freeze": {
                "h2_status": h2_summary.get("h2_status"),
                "research_decision": h2_final.get("research_decision"),
            },
        },
        "time_safety": {
            "uses_frozen_boundary_inputs_only": True,
            "input_hashes_recorded": True,
            "does_not_recompute_market_data": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_change_prior_research_conclusions": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "boundary_design_only": True,
            "does_not_generate_strategy": True,
            "does_not_select_assets": True,
            "does_not_map_etf": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_allocation": True,
            "does_not_optimize_parameters": True,
            "does_not_generate_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "requires_future_v12_evidence_before_implementation": True,
        },
        "forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }
    payload["audit"] = validate_research_to_implementation_boundary(payload)
    return payload


def write_research_to_implementation_boundary(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
