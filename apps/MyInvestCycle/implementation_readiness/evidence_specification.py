from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BOUNDARY_PATH = DATA_DIR / "research_to_implementation_boundary.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "implementation_readiness_evidence_specification.json"

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


def _component_spec(
    *,
    component_id: str,
    source_boundary_status: str,
    readiness_track: str,
    required_evidence: Sequence[str],
    failure_conditions: Sequence[str],
    minimum_observation_rule: str,
) -> dict[str, object]:
    return {
        "component_id": component_id,
        "source_boundary_status": source_boundary_status,
        "readiness_track": readiness_track,
        "readiness_status": "not_ready_evidence_required",
        "implementation_ready": False,
        "promotion_allowed": False,
        "evidence_current_status": "not_evaluated",
        "required_evidence": list(required_evidence),
        "failure_conditions": list(failure_conditions),
        "minimum_observation_rule": minimum_observation_rule,
    }


def validate_implementation_readiness_evidence_specification(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    schema = _mapping(payload.get("readiness_schema"))
    components = _sequence(payload.get("component_readiness_specifications"))
    gates = _sequence(payload.get("global_readiness_gates"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("readiness_specification_status") != "defined":
        raise AssertionError("readiness specification must be defined")
    if summary.get("implementation_readiness_status") != "not_ready":
        raise AssertionError("implementation readiness must remain not_ready")
    if summary.get("implementation_gate_result") != "blocked":
        raise AssertionError("implementation gate must remain blocked")
    if summary.get("any_component_implementation_ready") is not False:
        raise AssertionError("no component may be implementation ready")
    if summary.get("investable_output") is not False:
        raise AssertionError("investable output must remain false")
    if summary.get("strategy_output_generated") is not False:
        raise AssertionError("strategy output must remain false")
    if summary.get("allocation_output_generated") is not False:
        raise AssertionError("allocation output must remain false")
    if summary.get("trade_ready") is not False:
        raise AssertionError("trade_ready must remain false")
    if summary.get("conclusion") != "implementation_readiness_evidence_specification_defined_no_strategy_no_allocation":
        raise AssertionError("unexpected conclusion")

    if schema.get("current_specification_is_evaluation") is not False:
        raise AssertionError("schema must not evaluate evidence")
    if schema.get("current_specification_can_promote_component") is not False:
        raise AssertionError("schema must not promote components")
    if schema.get("all_requirements_must_be_future_verified") is not True:
        raise AssertionError("future verification requirement must be explicit")

    if len(components) != summary.get("component_spec_count"):
        raise AssertionError("component count mismatch")
    for component in components:
        if not isinstance(component, Mapping):
            raise AssertionError("component spec must be mapping")
        if component.get("implementation_ready") is not False:
            raise AssertionError(f"{component.get('component_id')} must not be ready")
        if component.get("promotion_allowed") is not False:
            raise AssertionError(f"{component.get('component_id')} promotion must be false")
        if component.get("evidence_current_status") != "not_evaluated":
            raise AssertionError(f"{component.get('component_id')} evidence must not be evaluated")
        if not _sequence(component.get("required_evidence")):
            raise AssertionError(f"{component.get('component_id')} missing required evidence")
        if not _sequence(component.get("failure_conditions")):
            raise AssertionError(f"{component.get('component_id')} missing failure conditions")

    if len(gates) != summary.get("global_gate_count"):
        raise AssertionError("global gate count mismatch")
    for gate in gates:
        if not isinstance(gate, Mapping):
            raise AssertionError("global gate must be mapping")
        if gate.get("current_status") != "not_evaluated":
            raise AssertionError(f"{gate.get('gate_id')} must not be evaluated")
        if gate.get("required_before_implementation") is not True:
            raise AssertionError(f"{gate.get('gate_id')} must be required")

    required_constraints = [
        "readiness_specification_only",
        "does_not_evaluate_evidence",
        "does_not_generate_strategy",
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

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(
        key for key in _walk_keys(payload) if key != "forbidden_outputs"
    )
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_readiness_status": summary.get("implementation_readiness_status"),
        "checked_component_specs": len(components),
        "checked_global_gates": len(gates),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_implementation_readiness_evidence_specification(
    *,
    boundary_path: str | Path = DEFAULT_BOUNDARY_PATH,
) -> dict[str, object]:
    boundary = _read_json(boundary_path)
    if not boundary:
        raise RuntimeError("V12.2 input missing; rebuild V12.1 research-to-implementation boundary first.")
    boundary_summary = _mapping(boundary.get("summary"))
    boundary_gate = _mapping(boundary.get("implementation_entry_gate"))
    boundary_components = [
        item for item in _sequence(boundary.get("component_boundaries")) if isinstance(item, Mapping)
    ]
    if boundary_summary.get("boundary_status") != "defined":
        raise RuntimeError("V12.1 boundary is not defined.")
    if boundary_gate.get("current_gate_result") != "blocked":
        raise RuntimeError("V12.1 implementation gate must be blocked before V12.2.")

    boundary_by_component = {
        str(item.get("component_id")): str(item.get("boundary_status") or "unknown")
        for item in boundary_components
    }
    common_failure_conditions = [
        "insufficient_out_of_sample_evidence",
        "unstable_across_market_structures",
        "unbounded_cost_or_turnover",
        "unresolved_future_function_or_data_lineage_risk",
    ]
    component_specs = [
        _component_spec(
            component_id="risk_diagnostic_layer",
            source_boundary_status=boundary_by_component.get("risk_diagnostic_layer", "unknown"),
            readiness_track="diagnostic_observation_to_shadow_monitoring",
            required_evidence=[
                "independent_out_of_sample_warning_effect",
                "false_warning_cost_estimate",
                "missed_risk_cost_estimate",
                "market_structure_stability_review",
                "live_shadow_observation_log",
            ],
            failure_conditions=[
                "warning_effect_reverses_in_holdout_window",
                "false_warning_cost_exceeds_protection_value",
                *common_failure_conditions,
            ],
            minimum_observation_rule="At least one future holdout cycle plus live shadow observation before any implementation review.",
        ),
        _component_spec(
            component_id="protection_research_value",
            source_boundary_status=boundary_by_component.get("protection_research_value", "unknown"),
            readiness_track="protection_evidence_to_policy_candidate",
            required_evidence=[
                "cross_regime_drawdown_reduction",
                "opportunity_cost_bound",
                "adverse_window_repeatability",
                "risk_event_definition_stability",
                "live_shadow_observation_log",
            ],
            failure_conditions=[
                "drawdown_reduction_not_repeatable",
                "opportunity_cost_exceeds_pre_registered_bound",
                *common_failure_conditions,
            ],
            minimum_observation_rule="Protection evidence must pass independent adverse and non-adverse windows.",
        ),
        _component_spec(
            component_id="contradiction_governance_layer",
            source_boundary_status=boundary_by_component.get("contradiction_governance_layer", "unknown"),
            readiness_track="research_governance_to_review_gate",
            required_evidence=[
                "decision_log_completeness",
                "contradiction_rule_stability",
                "human_review_reproducibility",
                "audit_trail_integrity",
            ],
            failure_conditions=[
                "governance_rule_changes_after_results",
                "reviewer_cannot_reproduce_decision",
                "audit_trail_missing_or_ambiguous",
            ],
            minimum_observation_rule="Governance rules must remain stable across future research reviews.",
        ),
        _component_spec(
            component_id="opportunity_prediction_layer",
            source_boundary_status=boundary_by_component.get("opportunity_prediction_layer", "unknown"),
            readiness_track="feature_research_to_prediction_candidate",
            required_evidence=[
                "positive_out_of_sample_information_coefficient",
                "feature_stability_by_market_structure",
                "proxy_to_tradable_migration_validation",
                "data_coverage_and_lag_audit",
                "negative_control_comparison",
            ],
            failure_conditions=[
                "information_coefficient_not_positive_after_split",
                "feature_sign_reversal_in_key_structure",
                "tradable_proxy_migration_fails",
                *common_failure_conditions,
            ],
            minimum_observation_rule="Opportunity prediction needs separate future validation before any scoring or ranking design.",
        ),
        _component_spec(
            component_id="allocation_alpha_layer",
            source_boundary_status=boundary_by_component.get("allocation_alpha_layer", "unknown"),
            readiness_track="research_hypothesis_to_allocation_candidate",
            required_evidence=[
                "positive_incremental_value_after_cost",
                "sample_split_robustness",
                "turnover_capacity_cost_model",
                "stress_window_loss_bound",
                "pre_registered_policy_comparison",
            ],
            failure_conditions=[
                "incremental_value_not_positive_after_cost",
                "performance_depends_on_single_window",
                "turnover_or_capacity_cost_unbounded",
                *common_failure_conditions,
            ],
            minimum_observation_rule="Allocation alpha must beat a pre-registered baseline after costs in future validation.",
        ),
        _component_spec(
            component_id="asset_selection_layer",
            source_boundary_status=boundary_by_component.get("asset_selection_layer", "unknown"),
            readiness_track="universe_research_to_selection_candidate",
            required_evidence=[
                "independent_universe_definition",
                "liquidity_tracking_error_audit",
                "survivorship_bias_audit",
                "constituent_or_fund_metadata_lineage",
            ],
            failure_conditions=[
                "universe_definition_depends_on_results",
                "liquidity_or_tracking_error_fails_threshold",
                "survivorship_bias_not_controlled",
            ],
            minimum_observation_rule="Universe research must be completed before any selection candidate exists.",
        ),
        _component_spec(
            component_id="portfolio_construction_layer",
            source_boundary_status=boundary_by_component.get("portfolio_construction_layer", "unknown"),
            readiness_track="risk_budget_to_portfolio_candidate",
            required_evidence=[
                "risk_budget_pre_registration",
                "turnover_and_transaction_cost_policy",
                "capacity_and_liquidity_stress_test",
                "rebalancing_failure_protocol",
                "human_review_before_promotion",
            ],
            failure_conditions=[
                "risk_budget_not_pre_registered",
                "stress_test_fails",
                "rebalancing_policy_depends_on_results",
            ],
            minimum_observation_rule="Portfolio construction requires a separate design review after research evidence is ready.",
        ),
        _component_spec(
            component_id="execution_layer",
            source_boundary_status=boundary_by_component.get("execution_layer", "unknown"),
            readiness_track="paper_sandbox_to_execution_candidate",
            required_evidence=[
                "paper_trading_sandbox_only",
                "broker_write_path_security_review",
                "explicit_user_authorization_record",
                "kill_switch_and_rollback_plan",
                "manual_approval_protocol",
            ],
            failure_conditions=[
                "broker_write_path_enabled_without_approval",
                "missing_kill_switch",
                "manual_approval_not_enforced",
            ],
            minimum_observation_rule="Execution cannot be considered until all upstream implementation components are independently ready.",
        ),
    ]
    global_gates = [
        {
            "gate_id": "data_lineage_and_time_safety",
            "required_before_implementation": True,
            "current_status": "not_evaluated",
            "pass_standard": "All implementation evidence must be generated with documented data dates, no future-function leakage and immutable input hashes.",
        },
        {
            "gate_id": "independent_out_of_sample_validation",
            "required_before_implementation": True,
            "current_status": "not_evaluated",
            "pass_standard": "Evidence must pass future holdout windows not used in research design.",
        },
        {
            "gate_id": "cost_turnover_capacity_review",
            "required_before_implementation": True,
            "current_status": "not_evaluated",
            "pass_standard": "Any candidate must remain positive after cost, turnover and capacity assumptions.",
        },
        {
            "gate_id": "live_shadow_observation",
            "required_before_implementation": True,
            "current_status": "not_evaluated",
            "pass_standard": "Candidate behavior must be logged in a no-trade shadow period before promotion.",
        },
        {
            "gate_id": "human_review_and_stop_conditions",
            "required_before_implementation": True,
            "current_status": "not_evaluated",
            "pass_standard": "A manual review must approve promotion and pre-register stop, rollback and failure criteria.",
        },
    ]
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V12.2 Implementation Readiness Evidence Specification",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(boundary.get("metadata")).get("as_of"),
            "input_files": {"research_to_implementation_boundary": _project_path(boundary_path)},
            "input_hashes": {"research_to_implementation_boundary": _file_hash(boundary_path)},
            "purpose": "Define evidence standards required before any future implementation-stage design can be considered, without evaluating evidence or creating investable outputs.",
        },
        "summary": {
            "readiness_specification_status": "defined",
            "implementation_readiness_status": "not_ready",
            "implementation_gate_result": "blocked",
            "component_spec_count": len(component_specs),
            "global_gate_count": len(global_gates),
            "any_component_implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "implementation_readiness_evidence_specification_defined_no_strategy_no_allocation",
            "key_read": "V12.2 defines future evidence standards only; no component is ready and no implementation, strategy, allocation or trading output is created.",
        },
        "readiness_schema": {
            "current_specification_is_evaluation": False,
            "current_specification_can_promote_component": False,
            "all_requirements_must_be_future_verified": True,
            "component_pass_rule": "A component can only be reviewed for implementation after all required evidence is independently generated, audited and manually approved in a future task.",
            "global_pass_rule": "All global gates must pass before any component can move beyond observation or governance use.",
            "allowed_current_status_values": ["not_evaluated", "evidence_required", "failed", "passed"],
            "current_status_used_here": "not_evaluated",
        },
        "component_readiness_specifications": component_specs,
        "global_readiness_gates": global_gates,
        "prohibited_shortcuts": [
            "research_phase_closure_cannot_count_as_implementation_evidence",
            "dashboard_label_cannot_trigger_allocation",
            "observation_only_status_cannot_be_promoted_without_future_evidence",
            "inconclusive_external_validation_cannot_be_reinterpreted_as_passed",
            "manual_review_cannot_be_skipped",
        ],
        "source_boundary_evidence": {
            "v12_1_boundary_status": boundary_summary.get("boundary_status"),
            "v12_1_implementation_phase": boundary_summary.get("implementation_phase"),
            "v12_1_gate_result": boundary_gate.get("current_gate_result"),
            "v12_1_component_count": boundary_summary.get("component_count"),
        },
        "time_safety": {
            "uses_v12_1_boundary_only": True,
            "input_hash_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_compute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_evaluate_evidence": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "readiness_specification_only": True,
            "does_not_evaluate_evidence": True,
            "does_not_generate_strategy": True,
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
    payload["audit"] = validate_implementation_readiness_evidence_specification(payload)
    return payload


def write_implementation_readiness_evidence_specification(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
