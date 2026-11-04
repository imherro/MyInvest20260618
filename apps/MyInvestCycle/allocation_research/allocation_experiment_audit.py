from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from allocation_research.allocation_experiment_schema import build_allocation_experiment_schema


DEFAULT_V9_3_PATH = DATA_DIR / "allocation_validation_plan.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_experiment_templates.json"

FORBIDDEN_OUTPUT_KEYS = {
    "asset_selection",
    "backtest_result",
    "broker_order",
    "buy_signal",
    "etf_mapping",
    "experiment_result",
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


def _question_for_hypothesis(hypothesis_id: str) -> str:
    questions = {
        "H1": "Can a predefined constructive research posture be evaluated against a waiting posture when risk relief and opportunity readiness improve?",
        "H2": "Can a predefined protection-first research posture be evaluated against an opportunity-seeking posture when risk evidence dominates?",
        "H3": "Can a predefined structure-aware research posture be evaluated against a broad-regime-only posture when structural opportunity evidence improves?",
        "H4": "Can a contradiction-gated research posture be evaluated against ungated promotion when known contradiction types recur?",
    }
    return questions.get(hypothesis_id, "Can this hypothesis be evaluated using only predeclared research postures?")


def _template_for_plan(plan: Mapping[str, Any], schema: Mapping[str, Any]) -> dict[str, object]:
    hypothesis_id = str(plan.get("hypothesis_id") or "unknown")
    return {
        "hypothesis_id": hypothesis_id,
        "hypothesis_name": plan.get("hypothesis_name"),
        "experiment_question": _question_for_hypothesis(hypothesis_id),
        "predefined_comparison": {
            "baseline": "baseline_research_posture",
            "alternative": "alternative_research_posture",
            "comparison_boundary": "Compare research postures only; do not define assets, ETFs, weights, exposure percentages, or trades.",
        },
        "evaluation_criteria": schema["required_evaluation_criteria"],
        "failure_criteria": plan.get("failure_criteria") or [],
        "anti_overfitting_rules": plan.get("anti_overfitting_rules") or [],
        "execution_status": schema["required_execution_status"],
        "forbidden_interpretation": "This template is not an experiment run, not a backtest result, not an optimization output, and not an investable allocation.",
    }


def validate_allocation_experiment_templates(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    schema = _mapping(payload.get("schema"))
    constraints = _mapping(payload.get("constraints"))
    templates = payload.get("experiment_templates")
    if not isinstance(templates, list) or not templates:
        raise AssertionError("experiment_templates must be a non-empty list")

    for key in (
        "experiment_template_ready",
        "experiment_executed",
        "ready_for_asset_selection",
        "ready_for_etf_mapping",
        "ready_for_weight_generation",
        "ready_for_backtest",
        "ready_for_validation_result",
        "ready_for_optimization",
        "ready_for_trade",
    ):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    required_constraints = [
        "research_only",
        "template_only",
        "does_not_execute_experiment",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_generate_portfolio_weight",
        "does_not_generate_exposure_percent",
        "does_not_run_backtest",
        "does_not_generate_result",
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

    required_criteria = set(str(item) for item in schema.get("required_evaluation_criteria", []))
    for template in templates:
        row = _mapping(template)
        if row.get("execution_status") != schema.get("required_execution_status"):
            raise AssertionError("all experiment templates must remain template_only_not_executed")
        if not required_criteria.issubset(set(str(item) for item in row.get("evaluation_criteria", []))):
            raise AssertionError(f"{row.get('hypothesis_id')} missing evaluation criteria")
        comparison = _mapping(row.get("predefined_comparison"))
        if comparison.get("baseline") != "baseline_research_posture":
            raise AssertionError(f"{row.get('hypothesis_id')} baseline comparison is invalid")
        if comparison.get("alternative") != "alternative_research_posture":
            raise AssertionError(f"{row.get('hypothesis_id')} alternative comparison is invalid")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(set(_walk_keys(payload)) - {"forbidden_outputs"})
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found outside schema.forbidden_outputs: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_template_count": len(templates),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_allocation_experiment_templates(
    *,
    v9_3_path: str | Path = DEFAULT_V9_3_PATH,
) -> dict[str, object]:
    validation_plan = _read_json(v9_3_path)
    if not validation_plan:
        raise RuntimeError("V9.4 input missing; run scripts/run_allocation_validation_plan.py first.")
    v9_summary = _mapping(validation_plan.get("summary"))
    v9_metadata = _mapping(validation_plan.get("metadata"))
    plans = validation_plan.get("validation_plans")
    if not isinstance(plans, list) or not plans:
        raise RuntimeError("V9.3 validation plans missing; rebuild allocation validation plan.")
    schema = build_allocation_experiment_schema()
    experiment_templates = [_template_for_plan(_mapping(plan), schema) for plan in plans]
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V9.4 Allocation Research Experiment Template Framework",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": v9_metadata.get("as_of"),
            "input_files": {
                "v9_3_allocation_validation_plan": _project_path(v9_3_path),
            },
            "purpose": "Define predefined research experiment templates without executing experiments or producing allocation outputs.",
        },
        "summary": {
            "source_context": v9_summary.get("source_context"),
            "source_conclusion": v9_summary.get("conclusion"),
            "validation_plan_count": v9_summary.get("validation_plan_count"),
            "experiment_template_count": len(experiment_templates),
            "executed_experiment_count": 0,
            "experiment_template_ready": False,
            "experiment_executed": False,
            "ready_for_asset_selection": False,
            "ready_for_etf_mapping": False,
            "ready_for_weight_generation": False,
            "ready_for_backtest": False,
            "ready_for_validation_result": False,
            "ready_for_optimization": False,
            "ready_for_trade": False,
            "conclusion": "allocation_experiment_templates_defined_not_executed",
            "key_read": "V9.4 defines experiment templates only; no experiment is run and no configuration, result, optimization, or trade output is produced.",
        },
        "schema": schema,
        "source_layer_evidence": {
            "v9_3_summary": v9_summary,
            "validation_plan_ids": [str(_mapping(plan).get("hypothesis_id")) for plan in plans],
        },
        "experiment_templates": experiment_templates,
        "time_safety": {
            "uses_v9_3_artifact_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "future_returns_not_used": True,
            "experiment_not_executed": True,
        },
        "data_quality": {
            "no_asset_data_loaded": True,
            "no_etf_data_loaded": True,
            "no_backtest": True,
            "no_parameter_scan": True,
            "no_optimization": True,
            "no_validation_result": True,
            "no_experiment_result": True,
        },
        "constraints": {
            "research_only": True,
            "template_only": True,
            "does_not_execute_experiment": True,
            "does_not_select_assets": True,
            "does_not_map_etf": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_exposure_percent": True,
            "does_not_run_backtest": True,
            "does_not_generate_result": True,
            "does_not_optimize_parameters": True,
            "no_buy_sell_signal": True,
            "no_rebalance_instruction": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }
    payload["audit"] = validate_allocation_experiment_templates(payload)
    return payload


def write_allocation_experiment_templates(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
