from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARCHITECTURE_DOC_PATH = ROOT_DIR / "implementation_readiness" / "architecture_freeze.md"
DEFAULT_V12_1_PATH = DATA_DIR / "research_to_implementation_boundary.json"
DEFAULT_V12_2_PATH = DATA_DIR / "implementation_readiness_evidence_specification.json"
DEFAULT_V12_3_PATH = DATA_DIR / "implementation_readiness_evidence_audit.json"
DEFAULT_V13_1_PATH = DATA_DIR / "research_component_evidence_submission_protocol.json"
DEFAULT_V13_2_PATH = DATA_DIR / "evidence_package_validation_engine.json"
DEFAULT_V13_3_PATH = DATA_DIR / "invalid_evidence_package_rejection_example.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "implementation_readiness_governance_freeze.json"

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


def _read_text(path: str | Path) -> str:
    target = Path(path)
    return target.read_text(encoding="utf-8") if target.exists() else ""


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


def validate_implementation_readiness_governance_freeze(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    stages = _sequence(payload.get("frozen_governance_chain"))
    boundaries = _mapping(payload.get("implementation_boundaries"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("governance_freeze_status") != "frozen":
        raise AssertionError("governance freeze status must be frozen")
    if summary.get("governance_chain_complete") is not True:
        raise AssertionError("governance chain must be complete")
    if summary.get("implementation_candidate_status") != "none_submitted":
        raise AssertionError("no implementation candidate may be submitted")
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
    if summary.get("project_completion_status") != "governance_frozen_project_not_complete":
        raise AssertionError("project completion boundary must remain explicit")
    if summary.get("conclusion") != "implementation_readiness_governance_frozen_no_strategy_no_allocation":
        raise AssertionError("unexpected conclusion")

    if len(stages) != summary.get("frozen_stage_count"):
        raise AssertionError("frozen stage count mismatch")
    for stage in stages:
        if not isinstance(stage, Mapping):
            raise AssertionError("stage must be mapping")
        if stage.get("status") != "frozen":
            raise AssertionError(f"{stage.get('stage_id')} must be frozen")
        if stage.get("implementation_ready") is not False:
            raise AssertionError(f"{stage.get('stage_id')} must not be implementation ready")

    for key in (
        "no_real_evidence_package_submitted",
        "no_component_promoted",
        "no_strategy_generated",
        "no_allocation_generated",
        "no_trade_path_enabled",
    ):
        if boundaries.get(key) is not True:
            raise AssertionError(f"implementation_boundaries.{key} must be true")

    required_constraints = [
        "governance_freeze_only",
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
        raise AssertionError(f"forbidden output keys found: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_governance_freeze_status": summary.get("governance_freeze_status"),
        "checked_stage_count": len(stages),
        "checked_project_completion_status": summary.get("project_completion_status"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_implementation_readiness_governance_freeze(
    *,
    architecture_doc_path: str | Path = DEFAULT_ARCHITECTURE_DOC_PATH,
    v12_1_path: str | Path = DEFAULT_V12_1_PATH,
    v12_2_path: str | Path = DEFAULT_V12_2_PATH,
    v12_3_path: str | Path = DEFAULT_V12_3_PATH,
    v13_1_path: str | Path = DEFAULT_V13_1_PATH,
    v13_2_path: str | Path = DEFAULT_V13_2_PATH,
    v13_3_path: str | Path = DEFAULT_V13_3_PATH,
) -> dict[str, object]:
    architecture_doc = _read_text(architecture_doc_path)
    v12_1 = _read_json(v12_1_path)
    v12_2 = _read_json(v12_2_path)
    v12_3 = _read_json(v12_3_path)
    v13_1 = _read_json(v13_1_path)
    v13_2 = _read_json(v13_2_path)
    v13_3 = _read_json(v13_3_path)
    if not all((architecture_doc, v12_1, v12_2, v12_3, v13_1, v13_2, v13_3)):
        raise RuntimeError("V13.4 inputs missing; rebuild V12.1-V13.3 governance artifacts first.")

    input_paths = {
        "architecture_freeze_doc": architecture_doc_path,
        "v12_1_boundary": v12_1_path,
        "v12_2_evidence_specification": v12_2_path,
        "v12_3_evidence_audit": v12_3_path,
        "v13_1_submission_protocol": v13_1_path,
        "v13_2_validation_engine": v13_2_path,
        "v13_3_rejection_test": v13_3_path,
    }
    stages = [
        ("V12.1", "research_to_implementation_boundary", _mapping(v12_1.get("summary")).get("boundary_status")),
        ("V12.2", "readiness_evidence_specification", _mapping(v12_2.get("summary")).get("readiness_specification_status")),
        ("V12.3", "readiness_evidence_audit_framework", _mapping(v12_3.get("summary")).get("audit_framework_status")),
        ("V13.1", "evidence_submission_protocol", _mapping(v13_1.get("summary")).get("protocol_status")),
        ("V13.2", "evidence_package_validation_engine", _mapping(v13_2.get("summary")).get("validation_engine_status")),
        ("V13.3", "invalid_package_rejection_test", _mapping(v13_3.get("summary")).get("example_status")),
    ]
    frozen_chain = [
        {
            "version": version,
            "stage_id": stage_id,
            "source_status": source_status,
            "status": "frozen",
            "implementation_ready": False,
        }
        for version, stage_id, source_status in stages
    ]
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V13.4 Implementation Readiness Governance Freeze",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(v13_3.get("metadata")).get("as_of"),
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Freeze the V12-V13 implementation readiness governance chain without submitting evidence or creating investable outputs.",
        },
        "summary": {
            "governance_freeze_status": "frozen",
            "governance_chain_complete": True,
            "frozen_stage_count": len(frozen_chain),
            "implementation_candidate_status": "none_submitted",
            "future_evidence_submission_supported": True,
            "implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "project_completion_status": "governance_frozen_project_not_complete",
            "conclusion": "implementation_readiness_governance_frozen_no_strategy_no_allocation",
            "key_read": "V12-V13 governance is frozen and ready to receive future single-component evidence packages, but no component is submitted, promoted or implementation-ready.",
        },
        "frozen_governance_chain": frozen_chain,
        "implementation_boundaries": {
            "no_real_evidence_package_submitted": True,
            "no_component_promoted": True,
            "no_strategy_generated": True,
            "no_allocation_generated": True,
            "no_trade_path_enabled": True,
            "future_work_must_choose_single_component": True,
            "future_package_must_use_v13_1_protocol": True,
            "future_package_must_pass_v13_2_validator": True,
            "future_package_must_pass_v12_3_audit": True,
        },
        "not_completed": [
            "real_component_evidence_submission",
            "implementation_candidate_review",
            "strategy_generation",
            "asset_or_fund_mapping",
            "portfolio_construction",
            "allocation_generation",
            "execution_or_trading",
        ],
        "recommended_next_phase": {
            "phase": "future_single_component_evidence_submission",
            "entry_condition": "User selects exactly one research component and submits a future evidence package through the frozen protocol.",
            "allowed_initial_components": [
                "risk_diagnostic_layer",
                "protection_research_value",
                "contradiction_governance_layer",
                "opportunity_prediction_layer",
                "allocation_alpha_layer",
                "asset_selection_layer",
                "portfolio_construction_layer",
                "execution_layer",
            ],
            "automatic_implementation_allowed": False,
        },
        "time_safety": {
            "uses_frozen_v12_to_v13_sources_only": True,
            "input_hashes_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_compute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_submit_or_evaluate_real_evidence": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "governance_freeze_only": True,
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
    payload["audit"] = validate_implementation_readiness_governance_freeze(payload)
    return payload


def write_implementation_readiness_governance_freeze(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
