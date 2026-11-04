from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from allocation_research.allocation_validation_plan_schema import build_allocation_validation_plan_schema


DEFAULT_V9_2_PATH = DATA_DIR / "allocation_research_hypotheses.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_validation_plan.json"

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
    "validation_result",
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


def _plan_for_hypothesis(hypothesis: Mapping[str, Any], schema: Mapping[str, Any]) -> dict[str, object]:
    hypothesis_id = str(hypothesis.get("id") or "unknown")
    base_objectives = {
        "H1": "Verify whether risk relief and improving opportunity readiness can be evaluated together without creating a configuration rule.",
        "H2": "Verify whether risk-dominant environments should prioritize protection-quality evidence before any later candidate promotion.",
        "H3": "Verify whether structural opportunity evidence can be confirmed independently from broad-market regime labels.",
        "H4": "Verify whether recurring contradiction types should block promotion from research hypothesis to any later candidate stage.",
    }
    base_failures = {
        "H1": [
            "out_of_sample_relationship_not_reproduced",
            "drawdown_audit_shows_risk_relief_unstable",
            "contradiction_audit_finds_false_participation_context",
        ],
        "H2": [
            "protection_quality_not_stable_out_of_sample",
            "opportunity_miss_contradictions_increase",
            "risk_dominance_signal_not_time_safe",
        ],
        "H3": [
            "structural_evidence_fails_time_safety",
            "broad_regime_explains_context_better",
            "walk_forward_design_cannot_separate_structure_from_broad_beta",
        ],
        "H4": [
            "contradiction_types_not_reproducible",
            "gate_too_sparse_for_research_use",
            "predeclared_failure_criteria_not_auditable",
        ],
    }
    return {
        "hypothesis_id": hypothesis_id,
        "hypothesis_name": hypothesis.get("name"),
        "validation_objective": base_objectives.get(hypothesis_id, "Define a research-only validation objective before any candidate promotion."),
        "required_evidence": schema["required_evidence"],
        "failure_criteria": base_failures.get(hypothesis_id, ["out_of_sample_design_not_reproducible"]),
        "anti_overfitting_rules": schema["required_anti_overfitting_rules"],
        "execution_status": schema["required_execution_status"],
        "forbidden_interpretation": "This plan must not be read as assets, ETFs, weights, exposure percentages, backtest results, optimization, or trades.",
    }


def validate_allocation_validation_plan(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    schema = _mapping(payload.get("schema"))
    constraints = _mapping(payload.get("constraints"))
    plans = payload.get("validation_plans")
    if not isinstance(plans, list) or not plans:
        raise AssertionError("validation_plans must be a non-empty list")

    for key in (
        "validation_plan_ready",
        "validation_executed",
        "ready_for_asset_selection",
        "ready_for_etf_mapping",
        "ready_for_weight_generation",
        "ready_for_backtest",
        "ready_for_optimization",
        "ready_for_trade",
    ):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    required_constraints = [
        "research_only",
        "plan_only",
        "does_not_execute_validation",
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

    required_evidence = set(str(item) for item in schema.get("required_evidence", []))
    anti_overfit = set(str(item) for item in schema.get("required_anti_overfitting_rules", []))
    for plan in plans:
        row = _mapping(plan)
        if row.get("execution_status") != schema.get("required_execution_status"):
            raise AssertionError("all validation plans must remain planned_not_executed")
        if not required_evidence.issubset(set(str(item) for item in row.get("required_evidence", []))):
            raise AssertionError(f"{row.get('hypothesis_id')} missing required evidence")
        if not anti_overfit.issubset(set(str(item) for item in row.get("anti_overfitting_rules", []))):
            raise AssertionError(f"{row.get('hypothesis_id')} missing anti-overfitting rules")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(set(_walk_keys(payload)) - {"forbidden_outputs"})
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found outside schema.forbidden_outputs: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_plan_count": len(plans),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_allocation_validation_plan(
    *,
    v9_2_path: str | Path = DEFAULT_V9_2_PATH,
) -> dict[str, object]:
    hypotheses_payload = _read_json(v9_2_path)
    if not hypotheses_payload:
        raise RuntimeError("V9.3 input missing; run scripts/run_allocation_hypothesis_audit.py first.")
    v9_summary = _mapping(hypotheses_payload.get("summary"))
    v9_metadata = _mapping(hypotheses_payload.get("metadata"))
    hypotheses = hypotheses_payload.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        raise RuntimeError("V9.2 hypotheses missing; rebuild allocation research hypotheses.")
    schema = build_allocation_validation_plan_schema()
    validation_plans = [_plan_for_hypothesis(_mapping(hypothesis), schema) for hypothesis in hypotheses]
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V9.3 Allocation Research Validation Plan Framework",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": v9_metadata.get("as_of"),
            "input_files": {
                "v9_2_allocation_research_hypotheses": _project_path(v9_2_path),
            },
            "purpose": "Design validation plans for V9.2 hypotheses without executing validation or producing investable outputs.",
        },
        "summary": {
            "source_context": v9_summary.get("source_context"),
            "source_conclusion": v9_summary.get("conclusion"),
            "hypothesis_count": len(hypotheses),
            "validation_plan_count": len(validation_plans),
            "executed_plan_count": 0,
            "validation_plan_ready": False,
            "validation_executed": False,
            "ready_for_asset_selection": False,
            "ready_for_etf_mapping": False,
            "ready_for_weight_generation": False,
            "ready_for_backtest": False,
            "ready_for_optimization": False,
            "ready_for_trade": False,
            "conclusion": "allocation_validation_plan_defined_not_executed",
            "key_read": "V9.3 defines validation plans only; it does not execute tests, produce results, optimize, or promote candidates.",
        },
        "schema": schema,
        "source_layer_evidence": {
            "v9_2_summary": v9_summary,
            "hypothesis_ids": [str(_mapping(hypothesis).get("id")) for hypothesis in hypotheses],
        },
        "validation_plans": validation_plans,
        "time_safety": {
            "uses_v9_2_artifact_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "future_returns_not_used": True,
            "validation_not_executed": True,
        },
        "data_quality": {
            "no_asset_data_loaded": True,
            "no_etf_data_loaded": True,
            "no_backtest": True,
            "no_parameter_scan": True,
            "no_optimization": True,
            "no_validation_result": True,
        },
        "constraints": {
            "research_only": True,
            "plan_only": True,
            "does_not_execute_validation": True,
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
    payload["audit"] = validate_allocation_validation_plan(payload)
    return payload


def write_allocation_validation_plan(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
