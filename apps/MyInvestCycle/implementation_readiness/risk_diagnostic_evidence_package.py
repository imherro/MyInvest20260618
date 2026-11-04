from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from implementation_readiness.evidence_package_validator import (
    FORBIDDEN_OUTPUT_KEYS,
    validate_future_evidence_package,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SUBMISSION_PROTOCOL_PATH = DATA_DIR / "research_component_evidence_submission_protocol.json"
DEFAULT_VALIDATION_ENGINE_PATH = DATA_DIR / "evidence_package_validation_engine.json"
DEFAULT_AUDIT_FRAMEWORK_PATH = DATA_DIR / "implementation_readiness_evidence_audit.json"
DEFAULT_GOVERNANCE_FREEZE_PATH = DATA_DIR / "implementation_readiness_governance_freeze.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_diagnostic_evidence_package.json"

RISK_COMPONENT_ID = "risk_diagnostic_layer"
REQUIRED_EVIDENCE_IDS = [
    "independent_out_of_sample_warning_effect",
    "false_warning_cost_estimate",
    "missed_risk_cost_estimate",
    "market_structure_stability_review",
    "live_shadow_observation_log",
]
SOURCE_PATHS = {
    "risk_gradient_robustness": DATA_DIR / "risk_gradient_robustness.json",
    "risk_gradient_condition_analysis": DATA_DIR / "risk_gradient_condition_analysis.json",
    "risk_gradient_candidate_rules": DATA_DIR / "risk_gradient_candidate_rules.json",
    "exposure_policy_validation": DATA_DIR / "exposure_policy_validation.json",
    "protection_score_validation": DATA_DIR / "protection_score_validation.json",
    "two_axis_context_validation": DATA_DIR / "two_axis_context_validation.json",
    "context_information_attribution": DATA_DIR / "context_information_attribution.json",
    "h2_external_validation_execution": DATA_DIR / "h2_external_validation_execution.json",
    "h2_external_validation_result_freeze": DATA_DIR / "h2_external_validation_result_freeze.json",
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


def _review_item(summary: Mapping[str, Any], item_type: str) -> Mapping[str, Any]:
    for item in _sequence(summary.get("review_items")):
        if isinstance(item, Mapping) and item.get("type") == item_type:
            return item
    return {}


def _review_evidence(summary: Mapping[str, Any], item_type: str) -> Mapping[str, Any]:
    return _mapping(_review_item(summary, item_type).get("evidence"))


def _source_record(source_id: str, path: Path, payload: Mapping[str, Any]) -> dict[str, object]:
    metadata = _mapping(payload.get("metadata"))
    return {
        "source_id": source_id,
        "path": _project_path(path),
        "hash": _file_hash(path),
        "engine": metadata.get("engine"),
        "as_of": metadata.get("as_of"),
    }


def _source_lineage(source_payloads: Mapping[str, Mapping[str, Any]]) -> list[dict[str, object]]:
    return [
        _source_record(source_id, SOURCE_PATHS[source_id], payload)
        for source_id, payload in source_payloads.items()
    ]


def _build_evidence_items(source_payloads: Mapping[str, Mapping[str, Any]]) -> list[dict[str, object]]:
    risk_summary = _mapping(source_payloads["risk_gradient_robustness"].get("summary"))
    condition_summary = _mapping(source_payloads["risk_gradient_condition_analysis"].get("summary"))
    exposure_summary = _mapping(source_payloads["exposure_policy_validation"].get("summary"))
    h2_summary = _mapping(source_payloads["h2_external_validation_result_freeze"].get("summary"))
    execution_summary = _mapping(source_payloads["h2_external_validation_execution"].get("summary"))

    false_warning = _review_evidence(exposure_summary, "high_false_warning_rate")
    missed_risk = _review_evidence(exposure_summary, "low_high_risk_capture_rate")
    robustness_warning = _review_evidence(risk_summary, "risk_gradient_not_robust_enough")

    return [
        {
            "evidence_id": "independent_out_of_sample_warning_effect",
            "evidence_status": "submitted_inconclusive",
            "source_files": [
                _project_path(SOURCE_PATHS["h2_external_validation_execution"]),
                _project_path(SOURCE_PATHS["h2_external_validation_result_freeze"]),
            ],
            "observations": {
                "target_hypothesis": h2_summary.get("target_hypothesis"),
                "external_status": h2_summary.get("h2_status"),
                "window_count": execution_summary.get("window_count"),
                "supported_count": h2_summary.get("evidence_supported_count"),
                "not_confirmed_count": h2_summary.get("evidence_not_confirmed_count"),
                "unresolved_count": h2_summary.get("evidence_unresolved_count"),
                "insufficient_count": h2_summary.get("evidence_insufficient_count"),
            },
            "finding": "External validation shows visible adverse-risk evidence, but stability is not broad enough for promotion.",
            "implementation_effect": "blocks_component_promotion",
        },
        {
            "evidence_id": "false_warning_cost_estimate",
            "evidence_status": "submitted_negative",
            "source_files": [_project_path(SOURCE_PATHS["exposure_policy_validation"])],
            "observations": {
                "false_warning_rate": false_warning.get("false_warning_rate"),
                "policy_validation_status": exposure_summary.get("policy_validation_status"),
            },
            "finding": "The fixed diagnostic flag has high false-warning cost in the current sample.",
            "implementation_effect": "blocks_policy_or_mapper_change",
        },
        {
            "evidence_id": "missed_risk_cost_estimate",
            "evidence_status": "submitted_negative",
            "source_files": [_project_path(SOURCE_PATHS["exposure_policy_validation"])],
            "observations": {
                "capture_rate": missed_risk.get("capture_rate"),
                "primary_candidate_count": exposure_summary.get("primary_candidate_count"),
            },
            "finding": "The fixed diagnostic flag captures only a small share of future high-risk events.",
            "implementation_effect": "blocks_policy_or_mapper_change",
        },
        {
            "evidence_id": "market_structure_stability_review",
            "evidence_status": "submitted_inconclusive",
            "source_files": [
                _project_path(SOURCE_PATHS["risk_gradient_robustness"]),
                _project_path(SOURCE_PATHS["risk_gradient_condition_analysis"]),
                _project_path(SOURCE_PATHS["risk_gradient_candidate_rules"]),
            ],
            "observations": {
                "period_consistency": risk_summary.get("period_consistency"),
                "overall_failure_rate": risk_summary.get("overall_failure_rate"),
                "overall_high_risk_lift": risk_summary.get("overall_high_risk_lift"),
                "positive_condition_count": condition_summary.get("positive_condition_count"),
                "insufficient_condition_count": condition_summary.get("insufficient_condition_count"),
                "robustness_warning": robustness_warning,
            },
            "finding": "Risk edge is visible in selected contexts, but cross-period robustness is insufficient.",
            "implementation_effect": "requires_more_shadow_and_external_observation",
        },
        {
            "evidence_id": "live_shadow_observation_log",
            "evidence_status": "submitted_missing_required_live_log",
            "source_files": [],
            "observations": {
                "live_shadow_observation_count": 0,
                "shadow_trade_enabled": False,
                "observation_status": "not_started_required_before_promotion",
            },
            "finding": "No live no-trade shadow observation log is available yet.",
            "implementation_effect": "blocks_implementation_readiness",
        },
    ]


def _build_validation_results(source_payloads: Mapping[str, Mapping[str, Any]]) -> list[dict[str, object]]:
    return [
        {
            "window_id": "h2_external_validation",
            "method": "frozen_external_validation_review",
            "pre_registered_metric": "adverse_risk_evidence_stability",
            "result_status": _mapping(source_payloads["h2_external_validation_result_freeze"].get("summary")).get("h2_status"),
            "lineage_hash": _file_hash(SOURCE_PATHS["h2_external_validation_result_freeze"]),
        },
        {
            "window_id": "risk_gradient_robustness",
            "method": "fixed_gradient_stability_audit",
            "pre_registered_metric": "period_consistency",
            "result_status": _mapping(source_payloads["risk_gradient_robustness"].get("summary")).get("conclusion"),
            "lineage_hash": _file_hash(SOURCE_PATHS["risk_gradient_robustness"]),
        },
        {
            "window_id": "conditional_risk_edge",
            "method": "fixed_context_condition_review",
            "pre_registered_metric": "conditional_high_risk_lift",
            "result_status": _mapping(source_payloads["risk_gradient_condition_analysis"].get("summary")).get("conclusion"),
            "lineage_hash": _file_hash(SOURCE_PATHS["risk_gradient_condition_analysis"]),
        },
        {
            "window_id": "policy_overlay_validation",
            "method": "diagnostic_overlay_validation_without_policy_change",
            "pre_registered_metric": "capture_rate_and_false_warning_rate",
            "result_status": _mapping(source_payloads["exposure_policy_validation"].get("summary")).get("policy_validation_status"),
            "lineage_hash": _file_hash(SOURCE_PATHS["exposure_policy_validation"]),
        },
        {
            "window_id": "two_axis_context_review",
            "method": "fixed_context_score_map_validation",
            "pre_registered_metric": "risk_spread_and_opportunity_spread",
            "result_status": _mapping(source_payloads["two_axis_context_validation"].get("summary")).get("conclusion"),
            "lineage_hash": _file_hash(SOURCE_PATHS["two_axis_context_validation"]),
        },
    ]


def validate_risk_diagnostic_evidence_package(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    metadata = _mapping(payload.get("package_metadata"))
    evidence_items = _sequence(payload.get("evidence_items"))
    validation_results = _sequence(payload.get("validation_results"))
    lineage = _mapping(payload.get("dataset_lineage"))
    shadow = _mapping(payload.get("shadow_observation_log"))
    human_review = _mapping(payload.get("human_review_record"))
    boundary_scan = _mapping(payload.get("boundary_violation_scan"))
    validator_result = _mapping(payload.get("v13_2_validator_result"))
    audit_projection = _mapping(payload.get("v12_3_audit_projection"))
    constraints = _mapping(payload.get("constraints"))

    if metadata.get("package_id") != "v14_1_risk_diagnostic_layer_phase0":
        raise AssertionError("unexpected package id")
    if payload.get("component_id") != RISK_COMPONENT_ID:
        raise AssertionError("component_id must be risk_diagnostic_layer")
    if summary.get("evidence_status") != "submitted":
        raise AssertionError("evidence status must be submitted")
    if summary.get("package_status") != "submitted_blocked_phase_0":
        raise AssertionError("package status must remain blocked")
    if summary.get("implementation_gate_result") != "blocked":
        raise AssertionError("implementation gate must be blocked")
    if summary.get("implementation_ready") is not False:
        raise AssertionError("implementation_ready must be false")
    if summary.get("investable_output") is not False:
        raise AssertionError("investable output must be false")
    if summary.get("strategy_output_generated") is not False:
        raise AssertionError("strategy output must be false")
    if summary.get("allocation_output_generated") is not False:
        raise AssertionError("allocation output must be false")
    if summary.get("trade_ready") is not False:
        raise AssertionError("trade_ready must be false")
    if summary.get("conclusion") != "risk_diagnostic_evidence_submitted_blocked_no_strategy_no_allocation":
        raise AssertionError("unexpected conclusion")

    received_ids = {
        str(item.get("evidence_id"))
        for item in evidence_items
        if isinstance(item, Mapping) and item.get("evidence_id")
    }
    if set(REQUIRED_EVIDENCE_IDS) != received_ids:
        raise AssertionError("risk diagnostic evidence ids mismatch")
    if len(validation_results) < 5:
        raise AssertionError("validation results must cover at least five frozen reviews")
    if lineage.get("lineage_status") != "frozen_sources_hashed":
        raise AssertionError("dataset lineage must be frozen and hashed")
    if shadow.get("observation_status") != "not_started_required_before_promotion":
        raise AssertionError("shadow observation must remain not started")
    if human_review.get("approval_status") != "not_approved_for_implementation":
        raise AssertionError("human review must not approve implementation")
    if human_review.get("stop_conditions_confirmed") is not True:
        raise AssertionError("stop conditions must be explicitly confirmed")

    if validator_result.get("package_status") != "format_valid_not_ready_for_implementation":
        raise AssertionError("V13.2 validator must accept format but block readiness")
    if validator_result.get("component_id_status") != "valid":
        raise AssertionError("component id must validate")
    if validator_result.get("implementation_ready") is not False:
        raise AssertionError("validator result must not be ready")
    if _sequence(validator_result.get("boundary_violations")):
        raise AssertionError("validator boundary violations must be absent")
    if validator_result.get("market_code_pattern_found") is not False:
        raise AssertionError("market code scan must remain false")
    if boundary_scan.get("scan_status") != "passed_no_investable_output":
        raise AssertionError("boundary scan must pass")
    if audit_projection.get("audit_decision") != "blocked_pending_shadow_and_manual_review":
        raise AssertionError("V12.3 projection must remain blocked")

    required_constraints = [
        "single_component_evidence_package_only",
        "submits_real_research_evidence",
        "does_not_promote_component",
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
        "checked_component_id": payload.get("component_id"),
        "checked_evidence_status": summary.get("evidence_status"),
        "checked_validator_package_status": validator_result.get("package_status"),
        "checked_audit_decision": audit_projection.get("audit_decision"),
        "checked_implementation_ready": summary.get("implementation_ready"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_risk_diagnostic_evidence_package(
    *,
    submission_protocol_path: str | Path = DEFAULT_SUBMISSION_PROTOCOL_PATH,
    validation_engine_path: str | Path = DEFAULT_VALIDATION_ENGINE_PATH,
    audit_framework_path: str | Path = DEFAULT_AUDIT_FRAMEWORK_PATH,
    governance_freeze_path: str | Path = DEFAULT_GOVERNANCE_FREEZE_PATH,
) -> dict[str, object]:
    protocol = _read_json(submission_protocol_path)
    validation_engine = _read_json(validation_engine_path)
    audit_framework = _read_json(audit_framework_path)
    governance_freeze = _read_json(governance_freeze_path)
    source_payloads = {source_id: _read_json(path) for source_id, path in SOURCE_PATHS.items()}
    if not all((protocol, validation_engine, audit_framework, governance_freeze, *source_payloads.values())):
        raise RuntimeError("V14.1 inputs missing; rebuild governance and risk diagnostic evidence artifacts first.")

    protocol_summary = _mapping(protocol.get("summary"))
    engine_summary = _mapping(validation_engine.get("summary"))
    governance_summary = _mapping(governance_freeze.get("summary"))
    if protocol_summary.get("protocol_status") != "defined":
        raise RuntimeError("V13.1 protocol must be defined before V14.1.")
    if engine_summary.get("validation_engine_status") != "defined":
        raise RuntimeError("V13.2 validation engine must be defined before V14.1.")
    if governance_summary.get("governance_freeze_status") != "frozen":
        raise RuntimeError("V13.4 governance freeze must be frozen before V14.1.")

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = _mapping(governance_freeze.get("metadata")).get("as_of")
    input_paths = {
        "v13_1_submission_protocol": submission_protocol_path,
        "v13_2_validation_engine": validation_engine_path,
        "v12_3_audit_framework": audit_framework_path,
        "v13_4_governance_freeze": governance_freeze_path,
        **SOURCE_PATHS,
    }
    input_files = {key: _project_path(path) for key, path in input_paths.items()}
    input_hashes = {key: _file_hash(path) for key, path in input_paths.items()}
    source_lineage = _source_lineage(source_payloads)
    evidence_items = _build_evidence_items(source_payloads)
    validation_results = _build_validation_results(source_payloads)

    payload: dict[str, object] = {
        "package_metadata": {
            "package_id": "v14_1_risk_diagnostic_layer_phase0",
            "component_id": RISK_COMPONENT_ID,
            "created_at": created_at,
            "market_data_as_of": as_of,
            "generator": "V14.1 Risk Diagnostic Layer Evidence Package Phase 0",
            "input_hashes": input_hashes,
        },
        "component_id": RISK_COMPONENT_ID,
        "summary": {
            "evidence_status": "submitted",
            "package_status": "submitted_blocked_phase_0",
            "component_id": RISK_COMPONENT_ID,
            "required_evidence_item_count": len(REQUIRED_EVIDENCE_IDS),
            "submitted_evidence_item_count": len(evidence_items),
            "validation_result_count": len(validation_results),
            "implementation_gate_result": "blocked",
            "implementation_ready": False,
            "manual_review_required": True,
            "shadow_observation_required": True,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "risk_diagnostic_evidence_submitted_blocked_no_strategy_no_allocation",
            "key_read": "Risk diagnostic evidence is submitted for governance testing, but false warnings, missed risks, cross-period instability and missing live shadow observation keep the component blocked.",
        },
        "evidence_items": evidence_items,
        "dataset_lineage": {
            "lineage_status": "frozen_sources_hashed",
            "market_data_as_of": as_of,
            "source_count": len(source_lineage),
            "source_files": source_lineage,
            "lineage_note": "V14.1 reads frozen research artifacts only and records their hashes; it does not recompute market features or forward labels.",
        },
        "validation_results": validation_results,
        "cost_turnover_capacity_review": {
            "review_status": "blocked_until_candidate_policy_exists",
            "cost_measured": False,
            "turnover_measured": False,
            "capacity_measured": False,
            "reason": "Risk diagnostic layer has no policy, asset mapping, allocation or trade path; cost and capacity review cannot pass until a later explicit candidate exists.",
        },
        "shadow_observation_log": {
            "observation_status": "not_started_required_before_promotion",
            "live_observation_count": 0,
            "shadow_trade_enabled": False,
            "required_before_promotion": True,
            "planned_checks": [
                "log_warning_events_without_trade",
                "compare_warning_to_later_risk_outcome",
                "record_false_warning_and_missed_risk_cases",
                "manual_review_before_any_promotion",
            ],
        },
        "human_review_record": {
            "reviewer": "codex_generated_for_chatgpt_audit",
            "review_time": created_at,
            "approval_status": "not_approved_for_implementation",
            "stop_conditions_confirmed": True,
            "review_note": "Phase 0 package is submitted for governance validation only; implementation promotion remains blocked.",
        },
        "boundary_violation_scan": {
            "scan_status": "pending_validator_scan",
            "market_code_pattern_found": None,
            "boundary_violations": [],
            "forbidden_output_key_found": None,
        },
        "input_hashes": input_hashes,
        "metadata": {
            "engine": "V14.1 Risk Diagnostic Layer Evidence Package Phase 0",
            "generated_at": created_at,
            "as_of": as_of,
            "input_files": input_files,
            "input_hashes": input_hashes,
            "purpose": "Submit the first single-component risk diagnostic evidence package through the frozen V13 protocol without promoting implementation or generating investable outputs.",
        },
        "source_governance": {
            "v13_1_protocol_status": protocol_summary.get("protocol_status"),
            "v13_2_validation_engine_status": engine_summary.get("validation_engine_status"),
            "v13_4_governance_freeze_status": governance_summary.get("governance_freeze_status"),
        },
        "v12_3_audit_projection": {
            "audit_status": "projected_blocked",
            "audit_decision": "blocked_pending_shadow_and_manual_review",
            "data_lineage_and_time_safety": "present",
            "independent_out_of_sample_validation": "inconclusive",
            "cost_turnover_capacity_review": "not_applicable_until_policy_candidate_exists",
            "live_shadow_observation": "missing_required_before_promotion",
            "human_review_and_stop_conditions": "not_approved_for_implementation",
            "implementation_ready": False,
        },
        "time_safety": {
            "uses_frozen_research_artifacts_only": True,
            "input_hashes_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "single_component_evidence_package_only": True,
            "submits_real_research_evidence": True,
            "does_not_promote_component": True,
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
    validator_result = validate_future_evidence_package(payload, protocol)
    payload["boundary_violation_scan"] = {
        "scan_status": "passed_no_investable_output",
        "validator_package_status": validator_result.get("package_status"),
        "validator_decision": validator_result.get("validation_decision"),
        "market_code_pattern_found": validator_result.get("market_code_pattern_found"),
        "boundary_violations": validator_result.get("boundary_violations"),
        "forbidden_output_key_found": "forbidden_output_key_detected" in _sequence(validator_result.get("boundary_violations")),
    }
    payload["v13_2_validator_result"] = validate_future_evidence_package(payload, protocol)
    payload["audit"] = validate_risk_diagnostic_evidence_package(payload)
    return payload


def write_risk_diagnostic_evidence_package(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
