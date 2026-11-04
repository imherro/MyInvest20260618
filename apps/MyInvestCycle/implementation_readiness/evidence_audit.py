from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SPECIFICATION_PATH = DATA_DIR / "implementation_readiness_evidence_specification.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "implementation_readiness_evidence_audit.json"

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


def _component_audit_template(component: Mapping[str, Any]) -> dict[str, object]:
    required = list(_sequence(component.get("required_evidence")))
    return {
        "component_id": component.get("component_id") or "unknown",
        "source_readiness_status": component.get("readiness_status") or "unknown",
        "audit_status": "not_submitted",
        "evidence_package_received": False,
        "evidence_items_received": [],
        "required_evidence_missing": required,
        "blocking_reasons": ["evidence_package_not_submitted"],
        "boundary_violation_found": False,
        "implementation_ready": False,
        "promotion_allowed": False,
        "audit_decision": "blocked_until_future_evidence_package_submitted",
    }


def validate_implementation_readiness_evidence_audit(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    schema = _mapping(payload.get("audit_schema"))
    components = _sequence(payload.get("component_audits"))
    global_gates = _sequence(payload.get("global_gate_audits"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("audit_framework_status") != "defined":
        raise AssertionError("audit framework must be defined")
    if summary.get("evidence_package_status") != "not_submitted":
        raise AssertionError("evidence package status must remain not_submitted")
    if summary.get("evidence_evaluation_status") != "not_started":
        raise AssertionError("evidence evaluation must not start")
    if summary.get("implementation_gate_result") != "blocked":
        raise AssertionError("implementation gate must remain blocked")
    if summary.get("implementation_ready_component_count") != 0:
        raise AssertionError("no component may be implementation ready")
    if summary.get("any_component_implementation_ready") is not False:
        raise AssertionError("any_component_implementation_ready must be false")
    if summary.get("investable_output") is not False:
        raise AssertionError("investable_output must be false")
    if summary.get("strategy_output_generated") is not False:
        raise AssertionError("strategy output must be false")
    if summary.get("allocation_output_generated") is not False:
        raise AssertionError("allocation output must be false")
    if summary.get("trade_ready") is not False:
        raise AssertionError("trade_ready must be false")
    if summary.get("conclusion") != "implementation_readiness_evidence_audit_framework_defined_no_strategy_no_allocation":
        raise AssertionError("unexpected conclusion")

    if schema.get("current_run_evaluates_submitted_evidence") is not False:
        raise AssertionError("current run must not evaluate submitted evidence")
    if schema.get("future_framework_can_audit_submitted_package") is not True:
        raise AssertionError("framework future audit role must be explicit")
    if schema.get("audit_can_promote_component_without_manual_review") is not False:
        raise AssertionError("manual review cannot be skipped")

    if len(components) != summary.get("component_audit_count"):
        raise AssertionError("component audit count mismatch")
    for item in components:
        if not isinstance(item, Mapping):
            raise AssertionError("component audit must be mapping")
        if item.get("audit_status") != "not_submitted":
            raise AssertionError(f"{item.get('component_id')} audit status must be not_submitted")
        if item.get("evidence_package_received") is not False:
            raise AssertionError(f"{item.get('component_id')} must not have evidence package")
        if not _sequence(item.get("required_evidence_missing")):
            raise AssertionError(f"{item.get('component_id')} missing evidence list required")
        if item.get("implementation_ready") is not False:
            raise AssertionError(f"{item.get('component_id')} must not be ready")
        if item.get("promotion_allowed") is not False:
            raise AssertionError(f"{item.get('component_id')} promotion must be false")
        if item.get("boundary_violation_found") is not False:
            raise AssertionError(f"{item.get('component_id')} must not report boundary violation without package")

    if len(global_gates) != summary.get("global_gate_audit_count"):
        raise AssertionError("global gate audit count mismatch")
    for item in global_gates:
        if not isinstance(item, Mapping):
            raise AssertionError("global gate audit must be mapping")
        if item.get("audit_status") != "not_submitted":
            raise AssertionError(f"{item.get('gate_id')} must be not_submitted")
        if item.get("gate_passed") is not False:
            raise AssertionError(f"{item.get('gate_id')} must not pass")

    required_constraints = [
        "audit_framework_only",
        "current_run_no_evidence_package",
        "does_not_evaluate_strategy_return",
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
        "checked_framework_status": summary.get("audit_framework_status"),
        "checked_evidence_package_status": summary.get("evidence_package_status"),
        "checked_component_audits": len(components),
        "checked_global_gate_audits": len(global_gates),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_implementation_readiness_evidence_audit(
    *,
    specification_path: str | Path = DEFAULT_SPECIFICATION_PATH,
) -> dict[str, object]:
    specification = _read_json(specification_path)
    if not specification:
        raise RuntimeError("V12.3 input missing; rebuild V12.2 implementation readiness evidence specification first.")
    summary = _mapping(specification.get("summary"))
    if summary.get("readiness_specification_status") != "defined":
        raise RuntimeError("V12.2 readiness specification is not defined.")
    if summary.get("implementation_gate_result") != "blocked":
        raise RuntimeError("V12.2 implementation gate must remain blocked before V12.3.")

    component_specs = [
        item
        for item in _sequence(specification.get("component_readiness_specifications"))
        if isinstance(item, Mapping)
    ]
    gate_specs = [
        item for item in _sequence(specification.get("global_readiness_gates")) if isinstance(item, Mapping)
    ]
    component_audits = [_component_audit_template(item) for item in component_specs]
    global_gate_audits = [
        {
            "gate_id": item.get("gate_id") or "unknown",
            "audit_status": "not_submitted",
            "required_before_implementation": item.get("required_before_implementation") is True,
            "gate_passed": False,
            "missing_evidence": [item.get("gate_id") or "unknown"],
            "pass_standard": item.get("pass_standard") or "",
        }
        for item in gate_specs
    ]

    payload: dict[str, object] = {
        "metadata": {
            "engine": "V12.3 Implementation Readiness Evidence Audit Framework",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(specification.get("metadata")).get("as_of"),
            "input_files": {"implementation_readiness_evidence_specification": _project_path(specification_path)},
            "input_hashes": {"implementation_readiness_evidence_specification": _file_hash(specification_path)},
            "purpose": "Define the framework for auditing future implementation readiness evidence packages while keeping the current run non-investable and not submitted.",
        },
        "summary": {
            "audit_framework_status": "defined",
            "evidence_package_status": "not_submitted",
            "evidence_evaluation_status": "not_started",
            "implementation_gate_result": "blocked",
            "component_audit_count": len(component_audits),
            "global_gate_audit_count": len(global_gate_audits),
            "submitted_component_count": 0,
            "implementation_ready_component_count": 0,
            "any_component_implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "implementation_readiness_evidence_audit_framework_defined_no_strategy_no_allocation",
            "key_read": "V12.3 defines how future evidence packages will be audited; no evidence package is submitted now, all components remain blocked, and no investable output is created.",
        },
        "audit_schema": {
            "current_run_evaluates_submitted_evidence": False,
            "future_framework_can_audit_submitted_package": True,
            "audit_can_promote_component_without_manual_review": False,
            "required_future_package_sections": [
                "component_id",
                "evidence_items",
                "data_lineage",
                "timestamps",
                "input_hashes",
                "validation_windows",
                "cost_turnover_capacity_review",
                "shadow_observation_log",
                "manual_review_record",
                "boundary_violation_scan",
            ],
            "automatic_rejection_conditions": [
                "missing_required_section",
                "missing_input_hash",
                "future_function_risk_detected",
                "forbidden_output_detected",
                "manual_review_missing",
                "broker_or_order_path_detected",
            ],
        },
        "component_audits": component_audits,
        "global_gate_audits": global_gate_audits,
        "future_package_contract": {
            "package_required": True,
            "current_package_present": False,
            "current_package_path": None,
            "review_scope": "future_submitted_evidence_only",
            "cannot_use_current_research_artifacts_as_substitute": True,
        },
        "source_specification_evidence": {
            "v12_2_readiness_specification_status": summary.get("readiness_specification_status"),
            "v12_2_implementation_readiness_status": summary.get("implementation_readiness_status"),
            "v12_2_gate_result": summary.get("implementation_gate_result"),
            "v12_2_component_spec_count": summary.get("component_spec_count"),
        },
        "time_safety": {
            "uses_v12_2_specification_only": True,
            "input_hash_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_compute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_evaluate_strategy_return": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "audit_framework_only": True,
            "current_run_no_evidence_package": True,
            "does_not_evaluate_strategy_return": True,
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
    payload["audit"] = validate_implementation_readiness_evidence_audit(payload)
    return payload


def write_implementation_readiness_evidence_audit(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
