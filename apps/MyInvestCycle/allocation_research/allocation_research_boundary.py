from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from allocation_research.allocation_research_schema import build_allocation_research_schema


DEFAULT_V6_CONTEXT_PATH = DATA_DIR / "two_axis_context_validation.json"
DEFAULT_V7_ARCHITECTURE_PATH = DATA_DIR / "opportunity_feature_attribution.json"
DEFAULT_V8_ARCHITECTURE_PATH = DATA_DIR / "research_decision_v8_architecture.json"
DEFAULT_V8_CONTEXT_PATH = DATA_DIR / "research_decision_context.json"
DEFAULT_V8_SCENARIO_PATH = DATA_DIR / "research_decision_scenario_audit.json"
DEFAULT_V8_CONTRADICTION_PATH = DATA_DIR / "research_decision_contradiction.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_research_architecture.json"


FORBIDDEN_OUTPUT_KEYS = {
    "asset_selection",
    "backtest_optimization",
    "broker_order",
    "etf_mapping",
    "portfolio_weight",
    "rebalance_instruction",
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


def _project_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


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


def validate_allocation_research_boundary(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    constraints = _mapping(payload.get("constraints"))
    data_quality = _mapping(payload.get("data_quality"))
    schema = _mapping(payload.get("schema"))

    for key in (
        "allocation_research_ready",
        "ready_for_asset_selection",
        "ready_for_etf_mapping",
        "ready_for_weight_generation",
        "ready_for_backtest",
        "ready_for_trade",
    ):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    required_constraints = [
        "architecture_only",
        "research_only",
        "does_not_generate_portfolio_weight",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_run_backtest",
        "does_not_optimize_parameters",
        "no_trade_signal",
        "no_order_generation",
        "no_broker_connection",
    ]
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")

    if data_quality.get("uses_frozen_v6_v7_v8_only") is not True:
        raise AssertionError("data_quality.uses_frozen_v6_v7_v8_only must be true")
    if data_quality.get("no_allocation_calculation") is not True:
        raise AssertionError("data_quality.no_allocation_calculation must be true")
    if data_quality.get("no_backtest") is not True:
        raise AssertionError("data_quality.no_backtest must be true")

    forbidden = schema.get("forbidden_outputs")
    if not isinstance(forbidden, list) or not FORBIDDEN_OUTPUT_KEYS.issubset(set(str(item) for item in forbidden)):
        raise AssertionError("schema.forbidden_outputs missing required forbidden outputs")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(set(_walk_keys(payload)) - {"forbidden_outputs"})
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found outside schema.forbidden_outputs: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_allocation_research_architecture(
    *,
    v6_context_path: str | Path = DEFAULT_V6_CONTEXT_PATH,
    v7_architecture_path: str | Path = DEFAULT_V7_ARCHITECTURE_PATH,
    v8_context_path: str | Path = DEFAULT_V8_CONTEXT_PATH,
    v8_scenario_path: str | Path = DEFAULT_V8_SCENARIO_PATH,
    v8_contradiction_path: str | Path = DEFAULT_V8_CONTRADICTION_PATH,
) -> dict[str, object]:
    v6_context = _read_json(v6_context_path)
    v7 = _read_json(v7_architecture_path)
    v8_context = _read_json(v8_context_path)
    v8_scenario = _read_json(v8_scenario_path)
    v8_contradiction = _read_json(v8_contradiction_path)
    if not all((v6_context, v7, v8_context, v8_scenario, v8_contradiction)):
        raise RuntimeError("V9.1 inputs missing; run frozen V6/V7/V8 builders first.")

    v6_summary = _mapping(v6_context.get("summary"))
    v7_summary = _mapping(v7.get("summary"))
    v8_context_summary = _mapping(v8_context.get("summary"))
    v8_scenario_summary = _mapping(v8_scenario.get("summary"))
    v8_contradiction_summary = _mapping(v8_contradiction.get("summary"))
    schema = build_allocation_research_schema()
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V9.1 Allocation Research Architecture Foundation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(v6_context.get("metadata")).get("as_of"),
            "input_files": {
                "v6_two_axis_context": _project_path(v6_context_path),
                "v7_opportunity_feature_attribution": _project_path(v7_architecture_path),
                "v8_research_decision_context": _project_path(v8_context_path),
                "v8_scenario_audit": _project_path(v8_scenario_path),
                "v8_contradiction_attribution": _project_path(v8_contradiction_path),
            },
            "purpose": "Define allocation research boundaries after frozen V6/V7/V8 layers; no portfolio weights, asset selection, ETF mapping, backtest optimization, or trades.",
        },
        "summary": {
            "environment_context": v8_context_summary.get("decision_context"),
            "risk_state": v6_summary.get("conclusion"),
            "opportunity_state": v7_summary.get("conclusion"),
            "research_interpretation_state": v8_contradiction_summary.get("conclusion"),
            "scenario_consistency_counts": v8_scenario_summary.get("consistency_counts") or {},
            "allocation_research_ready": False,
            "ready_for_asset_selection": False,
            "ready_for_etf_mapping": False,
            "ready_for_weight_generation": False,
            "ready_for_backtest": False,
            "ready_for_trade": False,
            "conclusion": "allocation_research_architecture_defined_not_ready",
            "key_read": "V9.1 defines the allocation research boundary only; it does not generate assets, ETF mappings, weights, backtests, or trades.",
        },
        "schema": schema,
        "source_layer_evidence": {
            "v6_risk_context": {
                "conclusion": v6_summary.get("conclusion"),
                "two_axis_risk_spread": v6_summary.get("two_axis_risk_spread"),
                "two_axis_opportunity_spread": v6_summary.get("two_axis_opportunity_spread"),
            },
            "v7_opportunity_research": {
                "conclusion": v7_summary.get("conclusion"),
                "retention_counts": v7_summary.get("retention_counts") or {},
            },
            "v8_research_interpretation": {
                "decision_context": v8_context_summary.get("decision_context"),
                "scenario_consistency_counts": v8_scenario_summary.get("consistency_counts") or {},
                "contradiction_type_counts": v8_contradiction_summary.get("contradiction_type_counts") or {},
            },
        },
        "time_safety": {
            "uses_frozen_v6_outputs_only": True,
            "uses_frozen_v7_outputs_only": True,
            "uses_frozen_v8_outputs_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
        },
        "data_quality": {
            "uses_frozen_v6_v7_v8_only": True,
            "no_allocation_calculation": True,
            "no_asset_selection": True,
            "no_etf_mapping": True,
            "no_weight_generation": True,
            "no_backtest": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "architecture_only": True,
            "research_only": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_select_assets": True,
            "does_not_map_etf": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "no_percentage_exposure": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }
    payload["audit"] = validate_allocation_research_boundary(payload)
    return payload


def write_allocation_research_architecture(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
