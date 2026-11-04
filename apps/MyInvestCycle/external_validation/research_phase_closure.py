from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_V6_ARCHITECTURE_PATH = ROOT_DIR / "docs" / "adaptive_exposure_v6_architecture.md"
DEFAULT_V7_ARCHITECTURE_PATH = ROOT_DIR / "docs" / "opportunity_research_v7_architecture.md"
DEFAULT_V8_ARCHITECTURE_PATH = ROOT_DIR / "docs" / "research_decision_v8_architecture.md"
DEFAULT_V10_BOUNDARY_PATH = DATA_DIR / "allocation_research_final_boundary.json"
DEFAULT_V11_H2_FREEZE_PATH = DATA_DIR / "h2_external_validation_result_freeze.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "research_phase_closure.json"

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


def validate_research_phase_closure(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    constraints = _mapping(payload.get("constraints"))
    if summary.get("research_phase") != "closed":
        raise AssertionError("research_phase must be closed")
    if summary.get("risk_research_status") != "validated_for_observation_only":
        raise AssertionError("risk_research_status must be observation-only")
    if summary.get("opportunity_research_status") != "not_ready":
        raise AssertionError("opportunity_research_status must be not_ready")
    if summary.get("allocation_status") != "not_ready":
        raise AssertionError("allocation_status must be not_ready")
    if summary.get("trading_status") != "disabled":
        raise AssertionError("trading_status must be disabled")
    if summary.get("project_completion_status") != "research_phase_closed_project_not_complete":
        raise AssertionError("project completion boundary must remain explicit")
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
        "phase_closure_only",
        "uses_frozen_v6_to_v11_sources_only",
        "does_not_add_research_layer",
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
        "checked_research_phase": summary.get("research_phase"),
        "checked_project_completion_status": summary.get("project_completion_status"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_research_phase_closure(
    *,
    v6_architecture_path: str | Path = DEFAULT_V6_ARCHITECTURE_PATH,
    v7_architecture_path: str | Path = DEFAULT_V7_ARCHITECTURE_PATH,
    v8_architecture_path: str | Path = DEFAULT_V8_ARCHITECTURE_PATH,
    v10_boundary_path: str | Path = DEFAULT_V10_BOUNDARY_PATH,
    v11_h2_freeze_path: str | Path = DEFAULT_V11_H2_FREEZE_PATH,
) -> dict[str, object]:
    v6_doc = _read_text(v6_architecture_path)
    v7_doc = _read_text(v7_architecture_path)
    v8_doc = _read_text(v8_architecture_path)
    v10_boundary = _read_json(v10_boundary_path)
    v11_h2 = _read_json(v11_h2_freeze_path)
    if not all((v6_doc, v7_doc, v8_doc, v10_boundary, v11_h2)):
        raise RuntimeError("V11.4 inputs missing; rebuild frozen V6-V11 artifacts first.")
    input_paths = {
        "v6_architecture": v6_architecture_path,
        "v7_architecture": v7_architecture_path,
        "v8_architecture": v8_architecture_path,
        "v10_final_boundary": v10_boundary_path,
        "v11_h2_result_freeze": v11_h2_freeze_path,
    }
    h2_summary = _mapping(v11_h2.get("summary"))
    h2_final = _mapping(v11_h2.get("final_conclusion"))
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V11.4 Research Phase Closure & Final Architecture Freeze",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(v11_h2.get("metadata")).get("as_of"),
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Close the V6-V11 research architecture phase without creating a strategy, allocation, asset, ETF, weight, optimization, or trading output.",
        },
        "summary": {
            "research_phase": "closed",
            "closure_status": "final_architecture_frozen",
            "risk_research_status": "validated_for_observation_only",
            "protection_research_status": "research_value_supported_observation_only",
            "contradiction_governance_status": "validated_for_research_governance_only",
            "opportunity_research_status": "not_ready",
            "allocation_status": "not_ready",
            "asset_selection_status": "disabled",
            "portfolio_construction_status": "not_ready",
            "trading_status": "disabled",
            "automatic_allocation_status": "disabled",
            "project_completion_status": "research_phase_closed_project_not_complete",
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
            "conclusion": "v6_to_v11_research_phase_closed_no_strategy_no_allocation",
            "key_read": "V6-V11 research architecture is closed; risk diagnostics are observation-only, opportunity and allocation remain not ready, trading remains disabled.",
        },
        "validated_for_observation_only": [
            {
                "layer": "risk_diagnostic_layer",
                "status": "validated_for_observation_only",
                "basis": "V6 risk architecture and V11 H2 freeze",
            },
            {
                "layer": "protection_research_value",
                "status": "supported_observation_only",
                "basis": "V6.4/V6.5/V11 H2 adverse-risk evidence",
            },
            {
                "layer": "contradiction_governance_value",
                "status": "supported_research_governance_only",
                "basis": "V8/V10 H4 governance boundary",
            },
        ],
        "not_verified_for_investment_use": [
            "opportunity_prediction",
            "allocation_alpha",
            "asset_selection",
            "portfolio_construction",
            "strategy_promotion",
            "automatic_allocation",
            "trading_signal_generation",
        ],
        "permanent_prohibitions": [
            "automatic_allocation",
            "automatic_trading",
            "broker_connection",
            "order_generation",
            "portfolio_weight_generation",
            "etf_mapping_for_execution",
            "asset_selection_for_execution",
            "parameter_optimization_for_investable_output",
        ],
        "phase_evidence": {
            "v6": {
                "status": "frozen",
                "role": "risk architecture and diagnostics",
                "source_present": bool(v6_doc),
            },
            "v7": {
                "status": "frozen",
                "role": "opportunity research foundation, not scoring or ranking",
                "source_present": bool(v7_doc),
            },
            "v8": {
                "status": "frozen",
                "role": "research interpretation and contradiction attribution",
                "source_present": bool(v8_doc),
            },
            "v9_v10": {
                "status": "frozen",
                "role": "allocation research governance and final boundary",
                "summary": v10_boundary.get("summary") or {},
            },
            "v11": {
                "status": "frozen",
                "role": "H2 external validation and final interpretation",
                "h2_status": h2_summary.get("h2_status"),
                "research_decision": h2_final.get("research_decision"),
            },
        },
        "time_safety": {
            "uses_frozen_v6_to_v11_sources_only": True,
            "input_hashes_recorded": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_market_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_add_research_layer": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "research_only": True,
            "phase_closure_only": True,
            "uses_frozen_v6_to_v11_sources_only": True,
            "does_not_add_research_layer": True,
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
    payload["audit"] = validate_research_phase_closure(payload)
    return payload


def write_research_phase_closure(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
