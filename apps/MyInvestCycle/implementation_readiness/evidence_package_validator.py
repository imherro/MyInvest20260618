from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from config import DATA_DIR


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SUBMISSION_PROTOCOL_PATH = DATA_DIR / "research_component_evidence_submission_protocol.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "evidence_package_validation_engine.json"

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
MARKET_CODE_PATTERN = re.compile(r"\b(?:[01356]\d{5})(?:\.(?:SH|SZ|CNI|CSI))?\b")


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


def _walk_items(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            items.append((path, item))
            items.extend(_walk_items(item, path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            items.append((path, item))
            items.extend(_walk_items(item, path))
    return items


def _walk_keys(value: Any) -> list[str]:
    return [path.rsplit(".", 1)[-1] for path, _ in _walk_items(value)]


def _allowed_components(protocol: Mapping[str, Any]) -> set[str]:
    contracts = _sequence(protocol.get("component_submission_contracts"))
    return {
        str(item.get("component_id"))
        for item in contracts
        if isinstance(item, Mapping) and item.get("component_id")
    }


def validate_future_evidence_package(
    package: Mapping[str, Any] | None,
    protocol: Mapping[str, Any],
) -> dict[str, object]:
    schema = _mapping(protocol.get("submission_schema"))
    required_fields = [str(item) for item in _sequence(schema.get("required_top_level_fields"))]
    allowed_components = _allowed_components(protocol)
    if package is None:
        return {
            "package_status": "invalid_not_submitted",
            "package_present": False,
            "component_id": None,
            "component_id_status": "not_checked",
            "missing_items": required_fields,
            "boundary_violations": [],
            "market_code_pattern_found": False,
            "implementation_ready": False,
            "validation_decision": "blocked_no_package_submitted",
        }

    missing_items = [field for field in required_fields if field not in package]
    component_id = package.get("component_id")
    component_id_status = "valid" if isinstance(component_id, str) and component_id in allowed_components else "invalid"
    forbidden_keys = sorted(FORBIDDEN_OUTPUT_KEYS.intersection(_walk_keys(package)))
    market_code_pattern_found = any(
        isinstance(value, str) and MARKET_CODE_PATTERN.search(value)
        for _, value in _walk_items(package)
    )
    boundary_violations = []
    if forbidden_keys:
        boundary_violations.append("forbidden_output_key_detected")
    if market_code_pattern_found:
        boundary_violations.append("market_code_pattern_detected")
    if component_id_status != "valid":
        boundary_violations.append("invalid_component_id")
    if missing_items:
        boundary_violations.append("missing_required_field")

    package_status = "format_valid_not_ready_for_implementation"
    if missing_items or boundary_violations:
        package_status = "invalid_missing_or_boundary_violation"

    return {
        "package_status": package_status,
        "package_present": True,
        "component_id": component_id if isinstance(component_id, str) else None,
        "component_id_status": component_id_status,
        "missing_items": missing_items,
        "boundary_violations": boundary_violations,
        "market_code_pattern_found": market_code_pattern_found,
        "implementation_ready": False,
        "validation_decision": "blocked_pending_manual_review_and_future_audit",
    }


def _component_validation_template(contract: Mapping[str, Any]) -> dict[str, object]:
    return {
        "component_id": contract.get("component_id") or "unknown",
        "package_status": "invalid_not_submitted",
        "package_present": False,
        "schema_checked": False,
        "boundary_checked": False,
        "implementation_ready": False,
        "validation_decision": "blocked_no_package_submitted",
    }


def validate_evidence_package_validation_engine(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    current_result = _mapping(payload.get("current_validation_result"))
    component_templates = _sequence(payload.get("component_validation_templates"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("validation_engine_status") != "defined":
        raise AssertionError("validation engine must be defined")
    if summary.get("current_package_status") != "invalid_not_submitted":
        raise AssertionError("current package status must be invalid_not_submitted")
    if summary.get("current_package_present") is not False:
        raise AssertionError("current package must be absent")
    if summary.get("implementation_gate_result") != "blocked":
        raise AssertionError("implementation gate must remain blocked")
    if summary.get("implementation_ready") is not False:
        raise AssertionError("implementation_ready must be false")
    if summary.get("investable_output") is not False:
        raise AssertionError("investable_output must be false")
    if summary.get("strategy_output_generated") is not False:
        raise AssertionError("strategy output must be false")
    if summary.get("allocation_output_generated") is not False:
        raise AssertionError("allocation output must be false")
    if summary.get("trade_ready") is not False:
        raise AssertionError("trade_ready must be false")
    if summary.get("conclusion") != "evidence_package_validation_engine_defined_no_strategy_no_allocation":
        raise AssertionError("unexpected conclusion")

    if current_result.get("package_status") != "invalid_not_submitted":
        raise AssertionError("current validation result must be invalid_not_submitted")
    if current_result.get("implementation_ready") is not False:
        raise AssertionError("current validation result must not be ready")
    if not _sequence(current_result.get("missing_items")):
        raise AssertionError("missing_items must list required fields")

    if len(component_templates) != summary.get("component_template_count"):
        raise AssertionError("component template count mismatch")
    for template in component_templates:
        if not isinstance(template, Mapping):
            raise AssertionError("component template must be mapping")
        if template.get("package_status") != "invalid_not_submitted":
            raise AssertionError(f"{template.get('component_id')} must be invalid_not_submitted")
        if template.get("implementation_ready") is not False:
            raise AssertionError(f"{template.get('component_id')} must not be ready")

    required_constraints = [
        "validation_engine_only",
        "current_run_no_real_package",
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
        "checked_engine_status": summary.get("validation_engine_status"),
        "checked_current_package_status": summary.get("current_package_status"),
        "checked_component_templates": len(component_templates),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_evidence_package_validation_engine(
    *,
    submission_protocol_path: str | Path = DEFAULT_SUBMISSION_PROTOCOL_PATH,
) -> dict[str, object]:
    protocol = _read_json(submission_protocol_path)
    if not protocol:
        raise RuntimeError("V13.2 input missing; rebuild V13.1 evidence submission protocol first.")
    summary = _mapping(protocol.get("summary"))
    if summary.get("protocol_status") != "defined":
        raise RuntimeError("V13.1 submission protocol is not defined.")
    if summary.get("implementation_gate_result") != "blocked":
        raise RuntimeError("V13.1 implementation gate must remain blocked before V13.2.")

    contracts = [
        item for item in _sequence(protocol.get("component_submission_contracts")) if isinstance(item, Mapping)
    ]
    current_result = validate_future_evidence_package(None, protocol)
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V13.2 Evidence Package Validation Engine",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(protocol.get("metadata")).get("as_of"),
            "input_files": {"research_component_evidence_submission_protocol": _project_path(submission_protocol_path)},
            "input_hashes": {"research_component_evidence_submission_protocol": _file_hash(submission_protocol_path)},
            "purpose": "Define the validation engine for future evidence packages without accepting real evidence or creating investable outputs in the current run.",
        },
        "summary": {
            "validation_engine_status": "defined",
            "current_package_status": current_result["package_status"],
            "current_package_present": False,
            "implementation_gate_result": "blocked",
            "component_template_count": len(contracts),
            "implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "evidence_package_validation_engine_defined_no_strategy_no_allocation",
            "key_read": "V13.2 defines automatic validation checks for future evidence packages; no real package is submitted now and implementation remains blocked.",
        },
        "validation_engine": {
            "current_run_accepts_real_package": False,
            "future_package_validation_supported": True,
            "can_promote_component_without_manual_review": False,
            "supported_checks": [
                "required_field_completeness",
                "component_id_membership",
                "input_hash_presence",
                "timestamp_presence",
                "data_lineage_presence",
                "validation_window_presence",
                "manual_review_presence",
                "forbidden_output_key_scan",
                "market_code_pattern_scan",
            ],
            "market_code_detection": "generic_market_code_pattern_only_no_code_list_output",
        },
        "current_validation_result": current_result,
        "component_validation_templates": [_component_validation_template(item) for item in contracts],
        "source_protocol_evidence": {
            "v13_1_protocol_status": summary.get("protocol_status"),
            "v13_1_submission_status": summary.get("submission_status"),
            "v13_1_package_created": summary.get("evidence_package_created"),
            "v13_1_component_contract_count": summary.get("component_contract_count"),
        },
        "time_safety": {
            "uses_v13_1_protocol_only": True,
            "input_hash_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_compute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_accept_real_package_in_current_run": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "validation_engine_only": True,
            "current_run_no_real_package": True,
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
    payload["audit"] = validate_evidence_package_validation_engine(payload)
    return payload


def write_evidence_package_validation_engine(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
