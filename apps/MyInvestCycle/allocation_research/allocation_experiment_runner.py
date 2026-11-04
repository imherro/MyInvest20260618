from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from allocation_research.allocation_experiment_result import build_allocation_experiment_result_schema


DEFAULT_V9_4_PATH = DATA_DIR / "allocation_experiment_templates.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_experiment_results_phase0.json"

FORBIDDEN_OUTPUT_KEYS = {
    "asset_selection",
    "backtest_result",
    "broker_order",
    "buy_signal",
    "etf_mapping",
    "exposure_percent",
    "optimization",
    "portfolio_weight",
    "rebalance_instruction",
    "sell_signal",
    "top_n",
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


def _phase0_result(template: Mapping[str, Any], schema: Mapping[str, Any]) -> dict[str, object]:
    evaluation_criteria = set(str(item) for item in template.get("evaluation_criteria", []))
    has_required_design = {
        "out_of_sample": "out_of_sample_design" in evaluation_criteria,
        "drawdown": "drawdown_audit_design" in evaluation_criteria,
        "contradiction": "contradiction_audit_design" in evaluation_criteria,
        "regime_stability": "regime_stability_design" in evaluation_criteria,
        "time_safety": "time_safety_design" in evaluation_criteria,
    }
    design_pass = all(has_required_design.values()) and template.get("execution_status") == "template_only_not_executed"
    return {
        "experiment_id": template.get("hypothesis_id"),
        "hypothesis_name": template.get("hypothesis_name"),
        "execution_status": schema["required_execution_status"],
        "validation_result": "design_pass_market_not_evaluated" if design_pass else "design_fail",
        "out_of_sample_status": "design_declared_not_measured" if has_required_design["out_of_sample"] else "missing_design",
        "drawdown_audit_status": "design_declared_not_measured" if has_required_design["drawdown"] else "missing_design",
        "contradiction_audit_status": "design_declared_not_measured" if has_required_design["contradiction"] else "missing_design",
        "regime_stability_status": "design_declared_not_measured" if has_required_design["regime_stability"] else "missing_design",
        "time_safety_status": "template_time_safe" if has_required_design["time_safety"] else "missing_design",
        "promotion_status": schema["required_promotion_status"],
        "investable_output": False,
        "interpretation": "Phase 0 executes design discipline only; market performance is not measured and no allocation candidate is promoted.",
    }


def validate_allocation_experiment_results(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    schema = _mapping(payload.get("schema"))
    constraints = _mapping(payload.get("constraints"))
    results = payload.get("experiment_results")
    if not isinstance(results, list) or not results:
        raise AssertionError("experiment_results must be a non-empty list")

    expected_false_flags = [
        "ready_for_asset_selection",
        "ready_for_etf_mapping",
        "ready_for_weight_generation",
        "ready_for_backtest",
        "ready_for_optimization",
        "ready_for_trade",
        "promoted_to_candidate",
        "investable_output_generated",
    ]
    for key in expected_false_flags:
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    required_constraints = [
        "research_only",
        "phase0_execution_only",
        "uses_predeclared_templates_only",
        "does_not_load_market_data",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_generate_portfolio_weight",
        "does_not_generate_exposure_percent",
        "does_not_run_backtest",
        "does_not_optimize_parameters",
        "no_buy_sell_signal",
        "no_rebalance_instruction",
        "no_order_generation",
        "no_broker_connection",
    ]
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")

    forbidden = schema.get("forbidden_outputs")
    if not isinstance(forbidden, list) or not FORBIDDEN_OUTPUT_KEYS.issubset(set(str(item) for item in forbidden)):
        raise AssertionError("schema.forbidden_outputs missing required forbidden outputs")

    allowed_results = set(str(item) for item in schema.get("allowed_validation_results", []))
    for row in results:
        result = _mapping(row)
        if result.get("execution_status") != schema.get("required_execution_status"):
            raise AssertionError("all Phase 0 experiments must be completed")
        if result.get("validation_result") not in allowed_results:
            raise AssertionError(f"{result.get('experiment_id')} has invalid validation_result")
        if result.get("promotion_status") != schema.get("required_promotion_status"):
            raise AssertionError("Phase 0 must not promote candidates")
        if result.get("investable_output") is not False:
            raise AssertionError("Phase 0 must not generate investable output")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(set(_walk_keys(payload)) - {"forbidden_outputs"})
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found outside schema.forbidden_outputs: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_result_count": len(results),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_allocation_experiment_results(
    *,
    v9_4_path: str | Path = DEFAULT_V9_4_PATH,
) -> dict[str, object]:
    templates_payload = _read_json(v9_4_path)
    if not templates_payload:
        raise RuntimeError("V9.5 input missing; run scripts/run_allocation_experiment_template.py first.")
    v9_summary = _mapping(templates_payload.get("summary"))
    v9_metadata = _mapping(templates_payload.get("metadata"))
    templates = templates_payload.get("experiment_templates")
    if not isinstance(templates, list) or not templates:
        raise RuntimeError("V9.4 experiment templates missing; rebuild allocation experiment templates.")
    schema = build_allocation_experiment_result_schema()
    experiment_results = [_phase0_result(_mapping(template), schema) for template in templates]
    design_pass_count = sum(1 for result in experiment_results if result["validation_result"] == "design_pass_market_not_evaluated")
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V9.5 Allocation Research Experiment Execution Phase 0",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": v9_metadata.get("as_of"),
            "input_files": {
                "v9_4_allocation_experiment_templates": _project_path(v9_4_path),
            },
            "purpose": "Execute predeclared research templates as Phase 0 design checks; no market data search, allocation, optimization, or trades.",
        },
        "summary": {
            "source_context": v9_summary.get("source_context"),
            "source_conclusion": v9_summary.get("conclusion"),
            "experiment_template_count": v9_summary.get("experiment_template_count"),
            "executed_experiment_count": len(experiment_results),
            "validation_result_count": len(experiment_results),
            "design_pass_count": design_pass_count,
            "design_fail_count": len(experiment_results) - design_pass_count,
            "market_validation_result_count": 0,
            "ready_for_asset_selection": False,
            "ready_for_etf_mapping": False,
            "ready_for_weight_generation": False,
            "ready_for_backtest": False,
            "ready_for_optimization": False,
            "ready_for_trade": False,
            "promoted_to_candidate": False,
            "investable_output_generated": False,
            "conclusion": "allocation_experiment_phase0_completed_research_only_not_investable",
            "key_read": "Phase 0 checks predeclared experiment discipline only; all results are non-investable and cannot be used for asset selection, ETF mapping, weights, optimization, or trades.",
        },
        "schema": schema,
        "source_layer_evidence": {
            "v9_4_summary": v9_summary,
            "experiment_ids": [str(_mapping(template).get("hypothesis_id")) for template in templates],
        },
        "execution_scope": {
            "phase": "phase0_design_execution",
            "market_data_loaded": False,
            "performance_measured": False,
            "parameter_search_performed": False,
            "candidate_promotion_allowed": False,
        },
        "experiment_results": experiment_results,
        "time_safety": {
            "uses_v9_4_artifact_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "future_returns_not_used": True,
            "market_data_not_loaded": True,
        },
        "data_quality": {
            "no_asset_data_loaded": True,
            "no_etf_data_loaded": True,
            "no_market_data_loaded": True,
            "no_backtest": True,
            "no_parameter_scan": True,
            "no_optimization": True,
        },
        "constraints": {
            "research_only": True,
            "phase0_execution_only": True,
            "uses_predeclared_templates_only": True,
            "does_not_load_market_data": True,
            "does_not_select_assets": True,
            "does_not_map_etf": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_exposure_percent": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "no_buy_sell_signal": True,
            "no_rebalance_instruction": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }
    payload["audit"] = validate_allocation_experiment_results(payload)
    return payload


def write_allocation_experiment_results(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
