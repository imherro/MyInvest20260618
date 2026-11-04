from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from external_validation.validation_protocol_schema import build_validation_protocol_schema


DEFAULT_FINAL_BOUNDARY_PATH = DATA_DIR / "allocation_research_final_boundary.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "external_validation_protocol.json"

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


def _build_protocol() -> dict[str, object]:
    return {
        "hypothesis_id": "H2",
        "source_status": "continue_external_validation",
        "protocol_status": "pre_registered",
        "validation_scope": {
            "purpose": "test whether the risk-protection research direction has external stability",
            "not_purpose": [
                "convert H2 into a strategy",
                "choose assets",
                "map ETF instruments",
                "generate portfolio weights",
                "create trade signals",
            ],
            "eligible_evidence": [
                "new time windows not used to decide V9-V10 boundaries",
                "new market phases with different trend and breadth backgrounds",
                "adverse periods where risk protection should matter",
                "benign periods where false protection should be limited",
            ],
        },
        "validation_windows": [
            {
                "window_id": "holdout_recent_window",
                "role": "recent unseen stability check",
                "must_be_declared_before_run": True,
                "result_use": "external_validation_only",
            },
            {
                "window_id": "regime_transition_window",
                "role": "stress check around market-state changes",
                "must_be_declared_before_run": True,
                "result_use": "external_validation_only",
            },
            {
                "window_id": "structural_bull_window",
                "role": "check that risk protection does not suppress structural opportunity without evidence",
                "must_be_declared_before_run": True,
                "result_use": "external_validation_only",
            },
            {
                "window_id": "adverse_risk_window",
                "role": "check whether protection evidence appears when drawdown risk is actually elevated",
                "must_be_declared_before_run": True,
                "result_use": "external_validation_only",
            },
        ],
        "pre_registered_methods": [
            {
                "method_id": "fixed_input_replay",
                "description": "replay fixed H2 evidence definitions without changing thresholds after results are observed",
                "allowed_result": "support_or_fail_research_direction_only",
            },
            {
                "method_id": "risk_separation_audit",
                "description": "compare high-risk and low-risk labels using pre-declared future validation labels",
                "allowed_result": "risk_separation_read_only",
            },
            {
                "method_id": "false_protection_audit",
                "description": "count cases where protection blocks participation in benign environments",
                "allowed_result": "failure_case_review_only",
            },
            {
                "method_id": "stability_by_market_phase",
                "description": "review whether H2 works across distinct market phases instead of only one period",
                "allowed_result": "phase_stability_review_only",
            },
        ],
        "failure_standards": [
            "fail if H2 only works in one narrow window and fails in other declared windows",
            "fail if false-protection cost dominates risk-protection evidence",
            "fail if a result requires changing thresholds after seeing validation outcomes",
            "fail if validation attempts to output assets, ETF mapping, weights, allocation, optimization, or trades",
            "fail if source data coverage gaps are hidden or replaced by stale data",
        ],
        "stop_conditions": [
            "stop if V10.3 final boundary input hash changes without a new protocol version",
            "stop if market data date and artifact generation date are not separated",
            "stop if an implementation introduces optimization or parameter search",
            "stop if any output can be interpreted as a trading instruction",
        ],
    }


def validate_external_validation_protocol(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    protocol = _mapping(payload.get("protocol"))
    excluded = _mapping(payload.get("excluded_directions"))
    constraints = _mapping(payload.get("constraints"))
    schema = _mapping(payload.get("schema"))
    if summary.get("protocol_phase_status") != "defined":
        raise AssertionError("protocol_phase_status must be defined")
    if summary.get("target_hypothesis") != "H2":
        raise AssertionError("target_hypothesis must be H2")
    if protocol.get("protocol_status") != "pre_registered":
        raise AssertionError("protocol must be pre_registered")
    if protocol.get("source_status") != "continue_external_validation":
        raise AssertionError("protocol source status must be continue_external_validation")
    if set(excluded.keys()) != {"H1", "H3", "H4"}:
        raise AssertionError("excluded directions must contain H1, H3, H4")
    for key in _sequence(schema.get("readiness_flags_required_false")):
        if summary.get(str(key)) is not False:
            raise AssertionError(f"summary.{key} must be false")
    required_constraints = [
        "research_only",
        "external_validation_protocol_only",
        "uses_v10_3_final_boundary_only",
        "does_not_run_external_validation",
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
        "checked_excluded_directions": sorted(excluded.keys()),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_external_validation_protocol(
    *,
    final_boundary_path: str | Path = DEFAULT_FINAL_BOUNDARY_PATH,
) -> dict[str, object]:
    final_boundary = _read_json(final_boundary_path)
    if not final_boundary:
        raise RuntimeError("V11.1 input missing; run scripts/run_allocation_research_final_boundary.py first.")
    directions = _mapping(final_boundary.get("directions"))
    h2 = _mapping(directions.get("H2"))
    if h2.get("status") != "continue_external_validation":
        raise RuntimeError("V11.1 requires V10.3 H2 status continue_external_validation.")
    schema = build_validation_protocol_schema()
    protocol = _build_protocol()
    excluded = {
        "H1": {
            "source_status": _mapping(directions.get("H1")).get("status"),
            "protocol_role": "excluded_frozen_no_external_validation",
        },
        "H3": {
            "source_status": _mapping(directions.get("H3")).get("status"),
            "protocol_role": "excluded_frozen_no_external_validation",
        },
        "H4": {
            "source_status": _mapping(directions.get("H4")).get("status"),
            "protocol_role": "research_governance_only_not_prediction_validation",
        },
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V11.1 External Validation Research Protocol",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "input_files": {
                "v10_3_final_boundary": _project_path(final_boundary_path),
            },
            "input_hashes": {
                "v10_3_final_boundary": _file_hash(final_boundary_path),
            },
            "purpose": "Define a pre-registered external validation protocol for H2 only without running validation or producing investable outputs.",
        },
        "schema": schema,
        "summary": {
            "protocol_phase_status": "defined",
            "target_hypothesis": "H2",
            "target_direction_count": 1,
            "excluded_direction_count": len(excluded),
            "protocol_ready_for_manual_external_validation": True,
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
            "conclusion": "h2_external_validation_protocol_defined_no_strategy_no_allocation",
            "key_read": "H2 can move to manual external validation protocol only; H4 remains governance-only; H1/H3 stay frozen.",
        },
        "protocol": protocol,
        "excluded_directions": excluded,
        "source_layer_evidence": {
            "v10_3_summary": final_boundary.get("summary") or {},
            "v10_3_h2": h2,
        },
        "time_safety": {
            "uses_v10_3_final_boundary_only": True,
            "input_hashes_recorded": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_market_backtest": True,
            "does_not_run_external_validation": True,
            "requires_pre_declared_windows_before_any_future_run": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "research_only": True,
            "external_validation_protocol_only": True,
            "uses_v10_3_final_boundary_only": True,
            "does_not_run_external_validation": True,
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
    payload["audit"] = validate_external_validation_protocol(payload)
    return payload


def write_external_validation_protocol(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
