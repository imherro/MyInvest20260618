from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from allocation_research.allocation_experiment_phase1_schema import build_allocation_experiment_phase1_schema


DEFAULT_V6_PATH = DATA_DIR / "two_axis_context_validation.json"
DEFAULT_V7_PATH = DATA_DIR / "opportunity_feature_attribution.json"
DEFAULT_V8_CONTEXT_PATH = DATA_DIR / "research_decision_context.json"
DEFAULT_V8_SCENARIO_PATH = DATA_DIR / "research_decision_scenario_audit.json"
DEFAULT_V8_CONTRADICTION_PATH = DATA_DIR / "research_decision_contradiction.json"
DEFAULT_V9_5_PATH = DATA_DIR / "allocation_experiment_results_phase0.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_experiment_phase1_validation.json"

FORBIDDEN_OUTPUT_KEYS = {
    "asset_selection",
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


def _sha256(path: str | Path) -> str:
    target = Path(path)
    return hashlib.sha256(target.read_bytes()).hexdigest()


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


def _validation_rows(
    *,
    v6_summary: Mapping[str, Any],
    v7_summary: Mapping[str, Any],
    v8_context_summary: Mapping[str, Any],
    v8_scenario_summary: Mapping[str, Any],
    v8_contradiction_summary: Mapping[str, Any],
    phase0_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, object]]:
    risk_spread = float(v6_summary.get("two_axis_risk_spread") or 0)
    opportunity_conclusion = str(v7_summary.get("conclusion") or "")
    contradiction_types = _mapping(v8_contradiction_summary.get("contradiction_type_counts"))
    consistency_counts = _mapping(v8_scenario_summary.get("consistency_counts"))
    phase0_by_id = {str(row.get("experiment_id")): row for row in phase0_results}

    def base_row(experiment_id: str, status: str, finding: str) -> dict[str, object]:
        phase0 = phase0_by_id.get(experiment_id, {})
        return {
            "experiment_id": experiment_id,
            "phase0_validation_result": phase0.get("validation_result"),
            "validation_status": status,
            "out_of_sample_status": "evaluated_from_frozen_scenario_audit",
            "drawdown_audit_status": "proxied_by_frozen_risk_context",
            "contradiction_audit_status": "evaluated_from_frozen_contradiction_attribution",
            "regime_stability_status": "evaluated_from_frozen_scenario_consistency",
            "time_safety_status": "frozen_artifact_hash_recorded",
            "promotion_allowed": False,
            "investable_output": False,
            "finding": finding,
        }

    h1_status = "inconclusive"
    h1_finding = "Risk context is measurable, but opportunity evidence remains not ready for an opportunity score."
    if opportunity_conclusion == "feature_attribution_ready_for_opportunity_score":
        h1_status = "supported"
        h1_finding = "Risk and opportunity evidence are both available in frozen artifacts."

    h2_status = "supported" if risk_spread > 0 else "inconclusive"
    h2_finding = "Risk axis remains visible and stronger than opportunity axis in frozen V6 evidence."

    structural_miss = int(contradiction_types.get("structural_market_opportunity_not_captured") or 0)
    h3_status = "inconclusive" if structural_miss else "unsupported"
    h3_finding = "Frozen V8 contradiction attribution still flags structural opportunity capture as an unresolved gap."

    contradiction_count = sum(int(value or 0) for value in contradiction_types.values())
    low_consistency_count = int(consistency_counts.get("low") or 0)
    h4_status = "supported" if contradiction_count and low_consistency_count else "inconclusive"
    h4_finding = "Frozen scenario audit and contradiction attribution support a contradiction-first promotion gate."

    return [
        base_row("H1", h1_status, h1_finding),
        base_row("H2", h2_status, h2_finding),
        base_row("H3", h3_status, h3_finding),
        base_row("H4", h4_status, h4_finding),
    ]


def validate_allocation_experiment_phase1_validation(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    schema = _mapping(payload.get("schema"))
    constraints = _mapping(payload.get("constraints"))
    freeze_hashes = _mapping(payload.get("freeze_hashes"))
    results = payload.get("validation_results")
    if not isinstance(results, list) or not results:
        raise AssertionError("validation_results must be a non-empty list")

    for key in (
        "ready_for_asset_selection",
        "ready_for_etf_mapping",
        "ready_for_weight_generation",
        "ready_for_optimization",
        "ready_for_trade",
        "promoted_to_candidate",
        "investable_output_generated",
    ):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    required_constraints = [
        "research_only",
        "phase1_validation_only",
        "uses_frozen_artifacts_only",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_generate_portfolio_weight",
        "does_not_generate_exposure_percent",
        "does_not_optimize_parameters",
        "no_buy_sell_signal",
        "no_rebalance_instruction",
        "no_order_generation",
        "no_broker_connection",
        "promotion_allowed_false",
    ]
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")

    if not freeze_hashes or any(len(str(value)) != 64 for value in freeze_hashes.values()):
        raise AssertionError("freeze_hashes must contain sha256 hashes")

    allowed_status = set(str(item) for item in schema.get("allowed_validation_status", []))
    for row in results:
        result = _mapping(row)
        if result.get("validation_status") not in allowed_status:
            raise AssertionError(f"{result.get('experiment_id')} invalid validation_status")
        if result.get("promotion_allowed") is not False:
            raise AssertionError("Phase 1 must keep promotion_allowed false")
        if result.get("investable_output") is not False:
            raise AssertionError("Phase 1 must not generate investable output")

    forbidden = schema.get("forbidden_outputs")
    if not isinstance(forbidden, list) or not FORBIDDEN_OUTPUT_KEYS.issubset(set(str(item) for item in forbidden)):
        raise AssertionError("schema.forbidden_outputs missing required forbidden outputs")
    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(set(_walk_keys(payload)) - {"forbidden_outputs"})
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found outside schema.forbidden_outputs: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_result_count": len(results),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_allocation_experiment_phase1_validation(
    *,
    v6_path: str | Path = DEFAULT_V6_PATH,
    v7_path: str | Path = DEFAULT_V7_PATH,
    v8_context_path: str | Path = DEFAULT_V8_CONTEXT_PATH,
    v8_scenario_path: str | Path = DEFAULT_V8_SCENARIO_PATH,
    v8_contradiction_path: str | Path = DEFAULT_V8_CONTRADICTION_PATH,
    v9_5_path: str | Path = DEFAULT_V9_5_PATH,
) -> dict[str, object]:
    v6 = _read_json(v6_path)
    v7 = _read_json(v7_path)
    v8_context = _read_json(v8_context_path)
    v8_scenario = _read_json(v8_scenario_path)
    v8_contradiction = _read_json(v8_contradiction_path)
    phase0 = _read_json(v9_5_path)
    if not all((v6, v7, v8_context, v8_scenario, v8_contradiction, phase0)):
        raise RuntimeError("V9.6 inputs missing; rebuild frozen V6/V7/V8 and V9.5 artifacts.")
    phase0_results = phase0.get("experiment_results")
    if not isinstance(phase0_results, list) or not phase0_results:
        raise RuntimeError("V9.5 experiment results missing.")

    v6_summary = _mapping(v6.get("summary"))
    v7_summary = _mapping(v7.get("summary"))
    v8_context_summary = _mapping(v8_context.get("summary"))
    v8_scenario_summary = _mapping(v8_scenario.get("summary"))
    v8_contradiction_summary = _mapping(v8_contradiction.get("summary"))
    schema = build_allocation_experiment_phase1_schema()
    validation_results = _validation_rows(
        v6_summary=v6_summary,
        v7_summary=v7_summary,
        v8_context_summary=v8_context_summary,
        v8_scenario_summary=v8_scenario_summary,
        v8_contradiction_summary=v8_contradiction_summary,
        phase0_results=[_mapping(row) for row in phase0_results],
    )
    status_counts = {
        status: sum(1 for row in validation_results if row["validation_status"] == status)
        for status in schema["allowed_validation_status"]
    }
    input_paths = {
        "v6_two_axis_context_validation": v6_path,
        "v7_opportunity_feature_attribution": v7_path,
        "v8_research_decision_context": v8_context_path,
        "v8_research_decision_scenario_audit": v8_scenario_path,
        "v8_research_decision_contradiction": v8_contradiction_path,
        "v9_5_phase0_experiment_results": v9_5_path,
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V9.6 Allocation Research Experiment Phase 1 Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(v6.get("metadata")).get("as_of"),
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "purpose": "Validate predeclared research experiments with frozen artifacts while forbidding investable outputs.",
        },
        "summary": {
            "source_context": v8_context_summary.get("decision_context"),
            "validation_result_count": len(validation_results),
            "supported_count": status_counts.get("supported", 0),
            "unsupported_count": status_counts.get("unsupported", 0),
            "inconclusive_count": status_counts.get("inconclusive", 0),
            "promotion_allowed": False,
            "ready_for_asset_selection": False,
            "ready_for_etf_mapping": False,
            "ready_for_weight_generation": False,
            "ready_for_optimization": False,
            "ready_for_trade": False,
            "promoted_to_candidate": False,
            "investable_output_generated": False,
            "conclusion": "allocation_experiment_phase1_validated_research_only_no_promotion",
            "key_read": "Phase 1 produces research validation statuses only; no asset selection, ETF mapping, weights, optimization, candidate promotion, or trades are allowed.",
        },
        "schema": schema,
        "freeze_hashes": {key: _sha256(path) for key, path in input_paths.items()},
        "source_layer_evidence": {
            "v6_conclusion": v6_summary.get("conclusion"),
            "v7_conclusion": v7_summary.get("conclusion"),
            "v8_decision_context": v8_context_summary.get("decision_context"),
            "v8_consistency_counts": v8_scenario_summary.get("consistency_counts") or {},
            "v8_contradiction_type_counts": v8_contradiction_summary.get("contradiction_type_counts") or {},
        },
        "validation_results": validation_results,
        "time_safety": {
            "uses_frozen_artifacts_only": True,
            "input_hashes_recorded": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "no_result_based_template_changes": True,
        },
        "data_quality": {
            "no_asset_selection": True,
            "no_etf_mapping": True,
            "no_weight_generation": True,
            "no_parameter_scan": True,
            "no_optimization": True,
            "phase1_outputs_research_only": True,
        },
        "constraints": {
            "research_only": True,
            "phase1_validation_only": True,
            "uses_frozen_artifacts_only": True,
            "does_not_select_assets": True,
            "does_not_map_etf": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_exposure_percent": True,
            "does_not_optimize_parameters": True,
            "no_buy_sell_signal": True,
            "no_rebalance_instruction": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "promotion_allowed_false": True,
        },
    }
    payload["audit"] = validate_allocation_experiment_phase1_validation(payload)
    return payload


def write_allocation_experiment_phase1_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
