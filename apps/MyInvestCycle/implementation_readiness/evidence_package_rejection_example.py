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
DEFAULT_VALIDATION_ENGINE_PATH = DATA_DIR / "evidence_package_validation_engine.json"
DEFAULT_SUBMISSION_PROTOCOL_PATH = DATA_DIR / "research_component_evidence_submission_protocol.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "invalid_evidence_package_rejection_example.json"


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


def _build_invalid_package() -> dict[str, object]:
    return {
        "package_metadata": {
            "package_id": "example_invalid_package",
            "component_id": "allocation_alpha_layer",
            "created_at": "example-only",
            "market_data_as_of": "example-only",
            "generator": "v13_3_invalid_case",
            "input_hashes": {},
        },
        "component_id": "allocation_alpha_layer",
        "evidence_items": [],
        "dataset_lineage": {"lineage_status": "missing_required_detail"},
        "validation_results": [],
        "input_hashes": {},
        "portfolio_weight": {"redacted": "forbidden_field_present_without_real_weight"},
    }


def validate_invalid_evidence_package_rejection_example(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    result = _mapping(payload.get("validator_result"))
    example = _mapping(payload.get("invalid_example_summary"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("example_status") != "generated":
        raise AssertionError("example must be generated")
    if summary.get("example_package_kind") != "invalid_blocked_case":
        raise AssertionError("example must be invalid blocked case")
    if summary.get("package_status") != "invalid_missing_or_boundary_violation":
        raise AssertionError("package status must be invalid")
    if summary.get("validation_decision") != "blocked_pending_manual_review_and_future_audit":
        raise AssertionError("validation decision must be blocked")
    if summary.get("implementation_ready") is not False:
        raise AssertionError("implementation_ready must be false")
    if summary.get("forbidden_output_detected") is not True:
        raise AssertionError("forbidden output must be detected")
    if summary.get("market_code_pattern_found") is not False:
        raise AssertionError("market code pattern must remain false")
    if summary.get("investable_output") is not False:
        raise AssertionError("investable output must be false")
    if summary.get("strategy_output_generated") is not False:
        raise AssertionError("strategy output must be false")
    if summary.get("allocation_output_generated") is not False:
        raise AssertionError("allocation output must be false")
    if summary.get("trade_ready") is not False:
        raise AssertionError("trade_ready must be false")
    if summary.get("conclusion") != "invalid_evidence_package_rejected_no_strategy_no_allocation":
        raise AssertionError("unexpected conclusion")

    if result.get("implementation_ready") is not False:
        raise AssertionError("validator result must not be ready")
    violations = set(str(item) for item in _sequence(result.get("boundary_violations")))
    if "missing_required_field" not in violations:
        raise AssertionError("missing field violation required")
    if "forbidden_output_key_detected" not in violations:
        raise AssertionError("forbidden output violation required")
    if not _sequence(result.get("missing_items")):
        raise AssertionError("missing items must be listed")

    if example.get("contains_real_market_code") is not False:
        raise AssertionError("example must not contain real market code")
    if example.get("contains_real_weight") is not False:
        raise AssertionError("example must not contain real weight")
    if example.get("redacted_forbidden_field_present") is not True:
        raise AssertionError("redacted forbidden field must be present")

    required_constraints = [
        "invalid_example_only",
        "does_not_submit_real_evidence",
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
        raise AssertionError(f"forbidden output keys found in final payload: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_package_status": summary.get("package_status"),
        "checked_validation_decision": summary.get("validation_decision"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_invalid_evidence_package_rejection_example(
    *,
    validation_engine_path: str | Path = DEFAULT_VALIDATION_ENGINE_PATH,
    submission_protocol_path: str | Path = DEFAULT_SUBMISSION_PROTOCOL_PATH,
) -> dict[str, object]:
    validation_engine = _read_json(validation_engine_path)
    protocol = _read_json(submission_protocol_path)
    if not validation_engine or not protocol:
        raise RuntimeError("V13.3 inputs missing; rebuild V13.1 and V13.2 artifacts first.")
    engine_summary = _mapping(validation_engine.get("summary"))
    protocol_summary = _mapping(protocol.get("summary"))
    if engine_summary.get("validation_engine_status") != "defined":
        raise RuntimeError("V13.2 validation engine is not defined.")
    if protocol_summary.get("protocol_status") != "defined":
        raise RuntimeError("V13.1 submission protocol is not defined.")

    invalid_package = _build_invalid_package()
    result = validate_future_evidence_package(invalid_package, protocol)
    input_paths = {
        "evidence_package_validation_engine": validation_engine_path,
        "research_component_evidence_submission_protocol": submission_protocol_path,
    }
    missing_items = list(_sequence(result.get("missing_items")))
    violations = list(_sequence(result.get("boundary_violations")))
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V13.3 Invalid Evidence Package Rejection Test",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(validation_engine.get("metadata")).get("as_of"),
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Prove the V13.2 validator blocks a synthetic invalid evidence package without using real strategy evidence or creating investable outputs.",
        },
        "summary": {
            "example_status": "generated",
            "example_package_kind": "invalid_blocked_case",
            "package_status": result.get("package_status"),
            "validation_decision": result.get("validation_decision"),
            "missing_item_count": len(missing_items),
            "boundary_violation_count": len(violations),
            "forbidden_output_detected": "forbidden_output_key_detected" in violations,
            "market_code_pattern_found": result.get("market_code_pattern_found"),
            "implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "invalid_evidence_package_rejected_no_strategy_no_allocation",
            "key_read": "A synthetic invalid evidence package is rejected because it misses required sections and contains a forbidden output field; no real evidence, asset code, weight, allocation or trade is created.",
        },
        "invalid_example_summary": {
            "package_id": "example_invalid_package",
            "component_id": "allocation_alpha_layer",
            "example_only": True,
            "contains_real_market_code": False,
            "contains_real_weight": False,
            "redacted_forbidden_field_present": True,
            "intentionally_missing_items": missing_items,
            "detected_boundary_violations": violations,
        },
        "validator_result": result,
        "source_engine_evidence": {
            "v13_2_validation_engine_status": engine_summary.get("validation_engine_status"),
            "v13_2_current_package_status": engine_summary.get("current_package_status"),
            "v13_2_implementation_ready": engine_summary.get("implementation_ready"),
            "v13_1_protocol_status": protocol_summary.get("protocol_status"),
        },
        "time_safety": {
            "uses_v13_1_and_v13_2_only": True,
            "input_hashes_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_compute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "uses_synthetic_invalid_package_only": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "invalid_example_only": True,
            "does_not_submit_real_evidence": True,
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
    payload["audit"] = validate_invalid_evidence_package_rejection_example(payload)
    return payload


def write_invalid_evidence_package_rejection_example(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
