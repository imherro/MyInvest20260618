from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


DEFAULT_EVIDENCE_FREEZE_PATH = DATA_DIR / "allocation_research_evidence_freeze.json"
DEFAULT_V6_RISK_PATH = DATA_DIR / "two_axis_context_validation.json"
DEFAULT_V7_OPPORTUNITY_PATH = DATA_DIR / "opportunity_feature_attribution.json"
DEFAULT_V8_CONTEXT_PATH = DATA_DIR / "research_decision_context.json"
DEFAULT_V8_SCENARIO_PATH = DATA_DIR / "research_decision_scenario_audit.json"
DEFAULT_V8_CONTRADICTION_PATH = DATA_DIR / "research_decision_contradiction.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_research_execution_runs.json"

ALLOWED_RESULT = {"supported", "inconclusive", "unsupported"}
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


def _run_input_hash(experiment_id: str, input_hashes: Mapping[str, str]) -> str:
    payload = json.dumps(
        {
            "experiment_id": experiment_id,
            "input_hashes": dict(sorted(input_hashes.items())),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def _retained_hypotheses(evidence_freeze: Mapping[str, object]) -> list[Mapping[str, Any]]:
    status = _mapping(evidence_freeze.get("hypothesis_status"))
    return [
        _mapping(status.get(hypothesis_id))
        for hypothesis_id in ("H2", "H4")
        if _mapping(status.get(hypothesis_id)).get("decision_boundary") == "retain_research_direction"
    ]


def _result_for_hypothesis(row: Mapping[str, Any]) -> str:
    status = row.get("status")
    if status == "supported_research_only":
        return "supported"
    if status == "inconclusive":
        return "inconclusive"
    return "unsupported"


def _evidence_checks_for_hypothesis(
    hypothesis_id: str,
    *,
    v6_summary: Mapping[str, Any],
    v7_summary: Mapping[str, Any],
    v8_context_summary: Mapping[str, Any],
    v8_scenario_summary: Mapping[str, Any],
    v8_contradiction_summary: Mapping[str, Any],
) -> dict[str, object]:
    if hypothesis_id == "H2":
        consistency_counts = _mapping(v8_scenario_summary.get("consistency_counts"))
        return {
            "risk_axis_status": v6_summary.get("conclusion"),
            "risk_spread": v6_summary.get("two_axis_risk_spread"),
            "opportunity_spread": v6_summary.get("two_axis_opportunity_spread"),
            "opportunity_status": v7_summary.get("conclusion"),
            "scenario_low_consistency_count": int(consistency_counts.get("low") or 0),
            "scenario_medium_consistency_count": int(consistency_counts.get("medium") or 0),
            "risk_axis_lag_case_count": int(
                _mapping(v8_contradiction_summary.get("possible_reason_counts")).get(
                    "risk_axis_lag_or_structural_rotation_missed"
                )
                or 0
            ),
            "result_basis": "frozen_evidence_supports_risk_attention_but_not_cross_scenario_stability",
        }
    return {
        "research_context": v8_context_summary.get("decision_context"),
        "focus_scenario_count": v8_contradiction_summary.get("focus_scenario_count"),
        "attribution_count": v8_contradiction_summary.get("attribution_count"),
        "contradiction_type_count": len(_mapping(v8_contradiction_summary.get("contradiction_type_counts"))),
        "result_basis": "frozen_contradiction_attribution_supports_research_gate_discipline_only",
    }


def _execution_run(
    row: Mapping[str, Any],
    *,
    as_of: object,
    input_hashes: Mapping[str, str],
    v6_summary: Mapping[str, Any],
    v7_summary: Mapping[str, Any],
    v8_context_summary: Mapping[str, Any],
    v8_scenario_summary: Mapping[str, Any],
    v8_contradiction_summary: Mapping[str, Any],
) -> dict[str, object]:
    experiment_id = str(row.get("hypothesis_id"))
    result = _result_for_hypothesis(row)
    return {
        "experiment_id": experiment_id,
        "run_id": f"V10_1_{experiment_id}_{as_of or 'unknown'}",
        "input_hash": _run_input_hash(experiment_id, input_hashes),
        "status": "completed",
        "result": result,
        "research_only": True,
        "source_hypothesis_status": row.get("status"),
        "execution_scope": "frozen_evidence_replay",
        "evidence_checks": _evidence_checks_for_hypothesis(
            experiment_id,
            v6_summary=v6_summary,
            v7_summary=v7_summary,
            v8_context_summary=v8_context_summary,
            v8_scenario_summary=v8_scenario_summary,
            v8_contradiction_summary=v8_contradiction_summary,
        ),
        "promotion_allowed": False,
        "strategy_promotion": False,
        "allocation_ready": False,
        "investable_output": False,
        "boundary": "Research execution record only; do not convert to assets, ETFs, weights, allocation, optimization, or trades.",
    }


def validate_allocation_research_execution_framework(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    runs = payload.get("execution_runs")
    constraints = _mapping(payload.get("constraints"))
    if not isinstance(runs, list) or len(runs) != 2:
        raise AssertionError("execution_runs must contain H2 and H4 only")
    if {str(_mapping(row).get("experiment_id")) for row in runs} != {"H2", "H4"}:
        raise AssertionError("execution_runs must contain H2 and H4")
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
    for row in runs:
        item = _mapping(row)
        if item.get("status") != "completed":
            raise AssertionError("execution run status must be completed")
        if item.get("result") not in ALLOWED_RESULT:
            raise AssertionError(f"{item.get('experiment_id')} invalid result")
        if len(str(item.get("input_hash") or "")) != 64:
            raise AssertionError("input_hash must be sha256 hex")
        if item.get("research_only") is not True:
            raise AssertionError("research_only must be true")
        for key in ("promotion_allowed", "strategy_promotion", "allocation_ready", "investable_output"):
            if item.get(key) is not False:
                raise AssertionError(f"{item.get('experiment_id')}.{key} must be false")

    required_constraints = [
        "research_only",
        "execution_framework_only",
        "uses_frozen_v9_9_evidence_only",
        "uses_frozen_v6_v7_v8_artifacts_only",
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
        "checked_run_count": len(runs),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_allocation_research_execution_framework(
    *,
    evidence_freeze_path: str | Path = DEFAULT_EVIDENCE_FREEZE_PATH,
    v6_risk_path: str | Path = DEFAULT_V6_RISK_PATH,
    v7_opportunity_path: str | Path = DEFAULT_V7_OPPORTUNITY_PATH,
    v8_context_path: str | Path = DEFAULT_V8_CONTEXT_PATH,
    v8_scenario_path: str | Path = DEFAULT_V8_SCENARIO_PATH,
    v8_contradiction_path: str | Path = DEFAULT_V8_CONTRADICTION_PATH,
) -> dict[str, object]:
    evidence_freeze = _read_json(evidence_freeze_path)
    v6_risk = _read_json(v6_risk_path)
    v7_opportunity = _read_json(v7_opportunity_path)
    v8_context = _read_json(v8_context_path)
    v8_scenario = _read_json(v8_scenario_path)
    v8_contradiction = _read_json(v8_contradiction_path)
    inputs = [evidence_freeze, v6_risk, v7_opportunity, v8_context, v8_scenario, v8_contradiction]
    if not all(inputs):
        raise RuntimeError("V10.1 inputs missing; rebuild V9.9 and frozen V6/V7/V8 artifacts first.")
    retained = _retained_hypotheses(evidence_freeze)
    if len(retained) != 2:
        raise RuntimeError("V10.1 expects exactly two retained research directions from V9.9.")

    input_paths = {
        "v9_9_evidence_freeze": evidence_freeze_path,
        "v6_risk": v6_risk_path,
        "v7_opportunity": v7_opportunity_path,
        "v8_context": v8_context_path,
        "v8_scenario": v8_scenario_path,
        "v8_contradiction": v8_contradiction_path,
    }
    input_hashes = {key: _file_hash(path) for key, path in input_paths.items()}
    evidence_summary = _mapping(evidence_freeze.get("summary"))
    as_of = _mapping(evidence_freeze.get("metadata")).get("as_of")
    v6_summary = _mapping(v6_risk.get("summary"))
    v7_summary = _mapping(v7_opportunity.get("summary"))
    v8_context_summary = _mapping(v8_context.get("summary"))
    v8_scenario_summary = _mapping(v8_scenario.get("summary"))
    v8_contradiction_summary = _mapping(v8_contradiction.get("summary"))
    runs = [
        _execution_run(
            row,
            as_of=as_of,
            input_hashes=input_hashes,
            v6_summary=v6_summary,
            v7_summary=v7_summary,
            v8_context_summary=v8_context_summary,
            v8_scenario_summary=v8_scenario_summary,
            v8_contradiction_summary=v8_contradiction_summary,
        )
        for row in retained
    ]
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V10.1 Allocation Research Execution Framework",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": as_of,
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": input_hashes,
            "purpose": "Execute frozen allocation research experiments as reproducible research records without producing asset, ETF, weight, allocation, optimization, or trade outputs.",
        },
        "summary": {
            "execution_phase": "V10.1",
            "source_research_state": evidence_summary.get("research_state"),
            "run_count": len(runs),
            "completed_run_count": sum(1 for row in runs if row["status"] == "completed"),
            "supported_count": sum(1 for row in runs if row["result"] == "supported"),
            "inconclusive_count": sum(1 for row in runs if row["result"] == "inconclusive"),
            "unsupported_count": sum(1 for row in runs if row["result"] == "unsupported"),
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
            "conclusion": "allocation_research_execution_records_completed_no_strategy_no_allocation",
            "key_read": "V10.1 creates reproducible research execution records for H2 and H4 only; H2 remains inconclusive and H4 supported research-only. No allocation or trading output is ready.",
        },
        "execution_runs": runs,
        "source_layer_evidence": {
            "v9_9_summary": evidence_summary,
            "v6_risk_summary": v6_summary,
            "v7_opportunity_summary": v7_summary,
            "v8_context_summary": v8_context_summary,
            "v8_scenario_summary": v8_scenario_summary,
            "v8_contradiction_summary": v8_contradiction_summary,
        },
        "time_safety": {
            "uses_frozen_v9_9_evidence_only": True,
            "uses_frozen_v6_v7_v8_artifacts_only": True,
            "input_hashes_recorded": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_market_backtest": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "research_only": True,
            "execution_framework_only": True,
            "uses_frozen_v9_9_evidence_only": True,
            "uses_frozen_v6_v7_v8_artifacts_only": True,
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
    payload["audit"] = validate_allocation_research_execution_framework(payload)
    return payload


def write_allocation_research_execution_framework(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
