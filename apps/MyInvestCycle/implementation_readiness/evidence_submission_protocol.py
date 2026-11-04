from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_FRAMEWORK_PATH = DATA_DIR / "implementation_readiness_evidence_audit.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "research_component_evidence_submission_protocol.json"

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


def _component_contract(component_id: str, required_evidence: Sequence[Any]) -> dict[str, object]:
    return {
        "component_id": component_id,
        "submission_scope": "future_evidence_package_only",
        "current_package_submitted": False,
        "submission_allowed_now": False,
        "required_evidence_items": list(required_evidence),
        "required_package_sections": [
            "component_id",
            "evidence_items",
            "dataset_lineage",
            "validation_results",
            "cost_turnover_capacity_review",
            "shadow_observation_log",
            "human_review_record",
            "boundary_violation_scan",
            "input_hashes",
        ],
        "forbidden_package_content": [
            "strategy_instruction",
            "asset_or_fund_code",
            "portfolio_or_allocation_output",
            "optimization_result",
            "broker_or_order_instruction",
        ],
        "initial_submission_status": "not_submitted",
        "promotion_allowed": False,
        "implementation_ready": False,
    }


def validate_research_component_evidence_submission_protocol(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    schema = _mapping(payload.get("submission_schema"))
    contracts = _sequence(payload.get("component_submission_contracts"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("protocol_status") != "defined":
        raise AssertionError("protocol must be defined")
    if summary.get("submission_status") != "not_submitted":
        raise AssertionError("submission status must remain not_submitted")
    if summary.get("evidence_package_created") is not False:
        raise AssertionError("evidence package must not be created")
    if summary.get("implementation_gate_result") != "blocked":
        raise AssertionError("implementation gate must remain blocked")
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
    if summary.get("conclusion") != "research_component_evidence_submission_protocol_defined_no_strategy_no_allocation":
        raise AssertionError("unexpected conclusion")

    if schema.get("current_run_submits_evidence_package") is not False:
        raise AssertionError("current run must not submit evidence package")
    if schema.get("future_package_required_for_audit") is not True:
        raise AssertionError("future package requirement must be explicit")
    if schema.get("protocol_can_promote_component") is not False:
        raise AssertionError("protocol cannot promote component")

    if len(contracts) != summary.get("component_contract_count"):
        raise AssertionError("component contract count mismatch")
    for contract in contracts:
        if not isinstance(contract, Mapping):
            raise AssertionError("component contract must be mapping")
        if contract.get("current_package_submitted") is not False:
            raise AssertionError(f"{contract.get('component_id')} must not be submitted")
        if contract.get("submission_allowed_now") is not False:
            raise AssertionError(f"{contract.get('component_id')} submission must not be allowed now")
        if contract.get("initial_submission_status") != "not_submitted":
            raise AssertionError(f"{contract.get('component_id')} initial status must be not_submitted")
        if contract.get("promotion_allowed") is not False:
            raise AssertionError(f"{contract.get('component_id')} promotion must be false")
        if contract.get("implementation_ready") is not False:
            raise AssertionError(f"{contract.get('component_id')} implementation ready must be false")
        if not _sequence(contract.get("required_package_sections")):
            raise AssertionError(f"{contract.get('component_id')} missing package sections")
        if not _sequence(contract.get("required_evidence_items")):
            raise AssertionError(f"{contract.get('component_id')} missing evidence items")

    required_constraints = [
        "submission_protocol_only",
        "current_run_no_submission",
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
        "checked_protocol_status": summary.get("protocol_status"),
        "checked_submission_status": summary.get("submission_status"),
        "checked_component_contracts": len(contracts),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_research_component_evidence_submission_protocol(
    *,
    audit_framework_path: str | Path = DEFAULT_AUDIT_FRAMEWORK_PATH,
) -> dict[str, object]:
    audit_framework = _read_json(audit_framework_path)
    if not audit_framework:
        raise RuntimeError("V13.1 input missing; rebuild V12.3 implementation readiness evidence audit first.")
    audit_summary = _mapping(audit_framework.get("summary"))
    if audit_summary.get("audit_framework_status") != "defined":
        raise RuntimeError("V12.3 audit framework is not defined.")
    if audit_summary.get("implementation_gate_result") != "blocked":
        raise RuntimeError("V12.3 implementation gate must remain blocked before V13.1.")

    component_audits = [
        item for item in _sequence(audit_framework.get("component_audits")) if isinstance(item, Mapping)
    ]
    contracts = [
        _component_contract(
            str(item.get("component_id") or "unknown"),
            _sequence(item.get("required_evidence_missing")),
        )
        for item in component_audits
    ]
    required_top_level_fields = [
        "package_metadata",
        "component_id",
        "evidence_items",
        "dataset_lineage",
        "validation_results",
        "cost_turnover_capacity_review",
        "shadow_observation_log",
        "human_review_record",
        "boundary_violation_scan",
        "input_hashes",
    ]
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V13.1 Research Component Evidence Submission Protocol",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(audit_framework.get("metadata")).get("as_of"),
            "input_files": {"implementation_readiness_evidence_audit": _project_path(audit_framework_path)},
            "input_hashes": {"implementation_readiness_evidence_audit": _file_hash(audit_framework_path)},
            "purpose": "Define the standard format for future research component evidence package submission without submitting evidence or creating investable outputs.",
        },
        "summary": {
            "protocol_status": "defined",
            "submission_status": "not_submitted",
            "evidence_package_created": False,
            "implementation_gate_result": "blocked",
            "component_contract_count": len(contracts),
            "required_top_level_field_count": len(required_top_level_fields),
            "implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "research_component_evidence_submission_protocol_defined_no_strategy_no_allocation",
            "key_read": "V13.1 defines future evidence package submission format only; no evidence is submitted, no component is promoted and no investable output is created.",
        },
        "submission_schema": {
            "schema_version": "v13.1",
            "current_run_submits_evidence_package": False,
            "future_package_required_for_audit": True,
            "protocol_can_promote_component": False,
            "required_top_level_fields": required_top_level_fields,
            "package_metadata_required_fields": [
                "package_id",
                "component_id",
                "created_at",
                "market_data_as_of",
                "generator",
                "input_hashes",
            ],
            "validation_result_required_fields": [
                "window_id",
                "method",
                "pre_registered_metric",
                "result_status",
                "lineage_hash",
            ],
            "manual_review_required_fields": [
                "reviewer",
                "review_time",
                "approval_status",
                "stop_conditions_confirmed",
            ],
        },
        "component_submission_contracts": contracts,
        "automatic_rejection_conditions": [
            "missing_required_top_level_field",
            "missing_input_hash",
            "component_id_not_in_protocol",
            "market_data_date_missing",
            "future_function_risk_not_addressed",
            "forbidden_package_content_detected",
            "manual_review_missing",
            "broker_or_order_path_included",
        ],
        "current_submission_state": {
            "package_present": False,
            "package_path": None,
            "submitted_component_count": 0,
            "accepted_component_count": 0,
            "rejected_component_count": 0,
            "implementation_ready_component_count": 0,
        },
        "source_audit_framework_evidence": {
            "v12_3_audit_framework_status": audit_summary.get("audit_framework_status"),
            "v12_3_evidence_package_status": audit_summary.get("evidence_package_status"),
            "v12_3_ready_component_count": audit_summary.get("implementation_ready_component_count"),
            "v12_3_gate_result": audit_summary.get("implementation_gate_result"),
        },
        "time_safety": {
            "uses_v12_3_audit_framework_only": True,
            "input_hash_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_compute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_submit_or_evaluate_evidence": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "submission_protocol_only": True,
            "current_run_no_submission": True,
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
    payload["audit"] = validate_research_component_evidence_submission_protocol(payload)
    return payload


def write_research_component_evidence_submission_protocol(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
