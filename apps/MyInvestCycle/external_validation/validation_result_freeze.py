from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


DEFAULT_EXECUTION_PATH = DATA_DIR / "h2_external_validation_execution.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "h2_external_validation_result_freeze.json"

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


def _run_by_window(execution: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("window_id")): _mapping(row)
        for row in _sequence(execution.get("validation_runs"))
        if isinstance(row, Mapping)
    }


def validate_h2_external_validation_result_freeze(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    conclusion = _mapping(payload.get("final_conclusion"))
    constraints = _mapping(payload.get("constraints"))
    if summary.get("freeze_status") != "frozen":
        raise AssertionError("freeze_status must be frozen")
    if summary.get("target_hypothesis") != "H2":
        raise AssertionError("target_hypothesis must be H2")
    if summary.get("h2_status") != "inconclusive":
        raise AssertionError("h2_status must be inconclusive")
    if conclusion.get("research_decision") != "continue_observation_only":
        raise AssertionError("research_decision must be continue_observation_only")
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
        if conclusion.get(key) is not False:
            raise AssertionError(f"final_conclusion.{key} must be false")

    required_constraints = [
        "research_only",
        "result_freeze_only",
        "uses_v11_2_execution_only",
        "does_not_modify_h2",
        "does_not_modify_risk_gradient",
        "does_not_change_thresholds",
        "does_not_add_features",
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
        "checked_target": "H2",
        "checked_h2_status": summary.get("h2_status"),
        "checked_research_decision": conclusion.get("research_decision"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_h2_external_validation_result_freeze(
    *,
    execution_path: str | Path = DEFAULT_EXECUTION_PATH,
) -> dict[str, object]:
    execution = _read_json(execution_path)
    if not execution:
        raise RuntimeError("V11.3 input missing; run scripts/run_h2_external_validation_execution.py first.")
    execution_summary = _mapping(execution.get("summary"))
    if execution_summary.get("target_hypothesis") != "H2":
        raise RuntimeError("V11.3 requires V11.2 H2 execution result.")
    if execution_summary.get("overall_status") != "inconclusive":
        raise RuntimeError("V11.3 expects H2 external validation to remain inconclusive.")
    windows = _run_by_window(execution)
    evidence = {
        "adverse_risk": {
            "status": "supported",
            "source_window": "adverse_risk_window",
            "source_status": _mapping(windows.get("adverse_risk_window")).get("status"),
            "interpretation": "risk diagnostics show visible value in adverse-risk conditions",
        },
        "cross_regime_stability": {
            "status": "not_confirmed",
            "source_window": "regime_transition_window",
            "source_status": _mapping(windows.get("regime_transition_window")).get("status"),
            "interpretation": "positive evidence is not stable enough across periods",
        },
        "recent_holdout": {
            "status": "insufficient",
            "source_window": "holdout_recent_window",
            "source_status": _mapping(windows.get("holdout_recent_window")).get("status"),
            "interpretation": "recent sample is too small for external support",
        },
        "structural_opportunity_conflict": {
            "status": "unresolved",
            "source_window": "structural_bull_window",
            "source_status": _mapping(windows.get("structural_bull_window")).get("status"),
            "interpretation": "false-protection risk during structural opportunity remains unresolved",
        },
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V11.3 H2 External Validation Result Freeze & Final Interpretation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(execution.get("metadata")).get("as_of"),
            "input_files": {
                "v11_2_execution": _project_path(execution_path),
            },
            "input_hashes": {
                "v11_2_execution": _file_hash(execution_path),
            },
            "purpose": "Freeze the final H2 external validation interpretation without modifying H2 or producing investable outputs.",
        },
        "summary": {
            "freeze_status": "frozen",
            "target_hypothesis": "H2",
            "h2_status": "inconclusive",
            "evidence_supported_count": 1,
            "evidence_not_confirmed_count": 1,
            "evidence_unresolved_count": 1,
            "evidence_insufficient_count": 1,
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
            "conclusion": "h2_external_validation_frozen_inconclusive_no_strategy_no_allocation",
            "key_read": "H2 has visible adverse-risk evidence, but cross-regime stability and structural-opportunity conflict are not resolved.",
        },
        "final_conclusion": {
            "H2_status": "inconclusive",
            "research_decision": "continue_observation_only",
            "interpretation": "H2 is useful as a risk-diagnostic research direction, not as an investable strategy or allocation rule.",
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
        },
        "evidence": evidence,
        "source_layer_evidence": {
            "v11_2_summary": execution_summary,
            "v11_2_validation_runs": execution.get("validation_runs") or [],
        },
        "time_safety": {
            "uses_v11_2_execution_only": True,
            "input_hashes_recorded": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_market_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_change_thresholds": True,
            "does_not_add_features": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "research_only": True,
            "result_freeze_only": True,
            "uses_v11_2_execution_only": True,
            "does_not_modify_h2": True,
            "does_not_modify_risk_gradient": True,
            "does_not_change_thresholds": True,
            "does_not_add_features": True,
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
    payload["audit"] = validate_h2_external_validation_result_freeze(payload)
    return payload


def write_h2_external_validation_result_freeze(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
