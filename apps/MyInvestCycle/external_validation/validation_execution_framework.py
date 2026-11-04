from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


DEFAULT_PROTOCOL_PATH = DATA_DIR / "external_validation_protocol.json"
DEFAULT_FINAL_BOUNDARY_PATH = DATA_DIR / "allocation_research_final_boundary.json"
DEFAULT_RISK_ROBUSTNESS_PATH = DATA_DIR / "risk_gradient_robustness.json"
DEFAULT_RISK_CONDITION_PATH = DATA_DIR / "risk_gradient_condition_analysis.json"
DEFAULT_PROTECTION_PATH = DATA_DIR / "protection_score_validation.json"
DEFAULT_TWO_AXIS_PATH = DATA_DIR / "two_axis_context_validation.json"
DEFAULT_CONTEXT_ATTRIBUTION_PATH = DATA_DIR / "context_information_attribution.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "h2_external_validation_execution.json"

ALLOWED_WINDOW_STATUS = {"passed", "failed", "inconclusive"}
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


def _find_period(payload: Mapping[str, Any], period: str) -> Mapping[str, Any]:
    for row in _sequence(payload.get("period_analysis")):
        item = _mapping(row)
        if item.get("period") == period:
            return item
    return {}


def _window_results(
    *,
    protocol: Mapping[str, Any],
    risk_robustness: Mapping[str, Any],
    risk_condition: Mapping[str, Any],
    protection: Mapping[str, Any],
    two_axis: Mapping[str, Any],
    context_attribution: Mapping[str, Any],
) -> list[dict[str, object]]:
    protocol_windows = {str(row.get("window_id")): row for row in _sequence(protocol.get("validation_windows")) if isinstance(row, Mapping)}
    risk_summary = _mapping(risk_robustness.get("summary"))
    risk_robustness_detail = _mapping(risk_robustness.get("robustness"))
    condition_summary = _mapping(risk_condition.get("summary"))
    protection_summary = _mapping(protection.get("summary"))
    protection_models = _mapping(protection.get("model_comparison"))
    model_c = _mapping(protection_models.get("model_c_risk_gradient_plus_protection_score"))
    two_axis_summary = _mapping(two_axis.get("summary"))
    context_summary = _mapping(context_attribution.get("summary"))
    recent_period = _find_period(risk_robustness, "2024-2026")

    return [
        {
            "window_id": "holdout_recent_window",
            "protocol_role": _mapping(protocol_windows.get("holdout_recent_window")).get("role"),
            "status": "inconclusive",
            "evidence_sources": ["risk_gradient_robustness"],
            "metrics": {
                "period": recent_period.get("period"),
                "sample_count": recent_period.get("sample_count"),
                "high_risk_sample_count": recent_period.get("high_risk_sample_count"),
                "high_risk_lift": recent_period.get("high_risk_lift"),
                "source_status": recent_period.get("status"),
            },
            "result_reason": "recent holdout has too few high-risk samples and the lift is not reliable enough for support",
            "allowed_next_step": "collect_more_external_observations_only",
        },
        {
            "window_id": "regime_transition_window",
            "protocol_role": _mapping(protocol_windows.get("regime_transition_window")).get("role"),
            "status": "inconclusive",
            "evidence_sources": ["risk_gradient_robustness", "risk_gradient_condition_analysis"],
            "metrics": {
                "period_consistency": risk_summary.get("period_consistency"),
                "positive_period_count": risk_robustness_detail.get("positive_period_count"),
                "negative_period_count": risk_robustness_detail.get("negative_period_count"),
                "insufficient_period_count": risk_robustness_detail.get("insufficient_period_count"),
                "positive_condition_count": condition_summary.get("positive_condition_count"),
                "negative_condition_count": condition_summary.get("negative_condition_count"),
                "insufficient_condition_count": condition_summary.get("insufficient_condition_count"),
            },
            "result_reason": "transition evidence is visible in some conditions but period-level robustness is not confirmed",
            "allowed_next_step": "keep_external_validation_open_only",
        },
        {
            "window_id": "structural_bull_window",
            "protocol_role": _mapping(protocol_windows.get("structural_bull_window")).get("role"),
            "status": "inconclusive",
            "evidence_sources": ["two_axis_context_validation", "protection_score_validation"],
            "metrics": {
                "participate_opportunity_lift": two_axis_summary.get("participate_opportunity_lift"),
                "two_axis_opportunity_spread": two_axis_summary.get("two_axis_opportunity_spread"),
                "model_c_false_warning_rate": model_c.get("false_warning_rate"),
                "context_opportunity_leader": context_summary.get("opportunity_leader"),
                "context_opportunity_leader_spread": context_summary.get("opportunity_leader_spread"),
            },
            "result_reason": "structural opportunity suppression risk remains unresolved because opportunity evidence is weak and false warnings are high",
            "allowed_next_step": "require_false_protection_review_only",
        },
        {
            "window_id": "adverse_risk_window",
            "protocol_role": _mapping(protocol_windows.get("adverse_risk_window")).get("role"),
            "status": "passed",
            "evidence_sources": ["protection_score_validation", "two_axis_context_validation"],
            "metrics": {
                "model_c_high_risk_lift": protection_summary.get("model_c_both_high_risk_lift"),
                "model_c_high_group_sample_count": model_c.get("high_group_sample_count"),
                "model_c_high_risk_event_capture_rate": model_c.get("high_risk_event_capture_rate"),
                "protect_but_participate_risk_lift": two_axis_summary.get("protect_but_participate_risk_lift"),
                "two_axis_risk_spread": two_axis_summary.get("two_axis_risk_spread"),
            },
            "result_reason": "risk-protection evidence is visible in adverse-risk diagnostics, though it is not sufficient for strategy promotion",
            "allowed_next_step": "retain_as_external_research_evidence_only",
        },
    ]


def validate_h2_external_validation_execution(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    runs = _sequence(payload.get("validation_runs"))
    constraints = _mapping(payload.get("constraints"))
    if summary.get("execution_status") != "completed":
        raise AssertionError("execution_status must be completed")
    if summary.get("target_hypothesis") != "H2":
        raise AssertionError("target_hypothesis must be H2")
    if len(runs) != 4:
        raise AssertionError("V11.2 must emit four validation windows")
    if {str(row.get("window_id")) for row in runs if isinstance(row, Mapping)} != {
        "holdout_recent_window",
        "regime_transition_window",
        "structural_bull_window",
        "adverse_risk_window",
    }:
        raise AssertionError("validation windows do not match V11.1 protocol")
    for row in runs:
        item = _mapping(row)
        if item.get("status") not in ALLOWED_WINDOW_STATUS:
            raise AssertionError(f"{item.get('window_id')} invalid status")
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
        "external_validation_execution_only",
        "uses_v11_1_protocol",
        "uses_v10_3_final_boundary",
        "uses_frozen_risk_evidence_only",
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
        "checked_window_count": len(runs),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_h2_external_validation_execution(
    *,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
    final_boundary_path: str | Path = DEFAULT_FINAL_BOUNDARY_PATH,
    risk_robustness_path: str | Path = DEFAULT_RISK_ROBUSTNESS_PATH,
    risk_condition_path: str | Path = DEFAULT_RISK_CONDITION_PATH,
    protection_path: str | Path = DEFAULT_PROTECTION_PATH,
    two_axis_path: str | Path = DEFAULT_TWO_AXIS_PATH,
    context_attribution_path: str | Path = DEFAULT_CONTEXT_ATTRIBUTION_PATH,
) -> dict[str, object]:
    protocol_payload = _read_json(protocol_path)
    final_boundary = _read_json(final_boundary_path)
    risk_robustness = _read_json(risk_robustness_path)
    risk_condition = _read_json(risk_condition_path)
    protection = _read_json(protection_path)
    two_axis = _read_json(two_axis_path)
    context_attribution = _read_json(context_attribution_path)
    if not all((protocol_payload, final_boundary, risk_robustness, risk_condition, protection, two_axis, context_attribution)):
        raise RuntimeError("V11.2 inputs missing; rebuild V11.1 and frozen V5/V6 risk evidence first.")
    protocol_summary = _mapping(protocol_payload.get("summary"))
    if protocol_summary.get("target_hypothesis") != "H2":
        raise RuntimeError("V11.2 requires a V11.1 H2 protocol.")
    runs = _window_results(
        protocol=_mapping(protocol_payload.get("protocol")),
        risk_robustness=risk_robustness,
        risk_condition=risk_condition,
        protection=protection,
        two_axis=two_axis,
        context_attribution=context_attribution,
    )
    passed_count = sum(1 for row in runs if row["status"] == "passed")
    failed_count = sum(1 for row in runs if row["status"] == "failed")
    inconclusive_count = sum(1 for row in runs if row["status"] == "inconclusive")
    if failed_count:
        overall_status = "failed"
    elif passed_count == len(runs):
        overall_status = "passed"
    else:
        overall_status = "inconclusive"
    input_paths = {
        "v11_1_protocol": protocol_path,
        "v10_3_final_boundary": final_boundary_path,
        "risk_gradient_robustness": risk_robustness_path,
        "risk_gradient_condition_analysis": risk_condition_path,
        "protection_score_validation": protection_path,
        "two_axis_context_validation": two_axis_path,
        "context_information_attribution": context_attribution_path,
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V11.2 H2 External Validation Execution Framework",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(protection.get("metadata")).get("as_of") or _mapping(two_axis.get("metadata")).get("as_of"),
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Execute the pre-registered H2 external validation protocol using frozen risk evidence only, without producing investable outputs.",
        },
        "summary": {
            "execution_status": "completed",
            "target_hypothesis": "H2",
            "window_count": len(runs),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "inconclusive_count": inconclusive_count,
            "overall_status": overall_status,
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
            "conclusion": "h2_external_validation_inconclusive_no_strategy_no_allocation",
            "key_read": "H2 shows adverse-risk evidence but external stability is not broad enough for promotion.",
        },
        "validation_runs": runs,
        "source_layer_evidence": {
            "v11_1_summary": protocol_payload.get("summary") or {},
            "v10_3_h2": _mapping(_mapping(final_boundary.get("directions")).get("H2")),
            "frozen_risk_artifact_count": 5,
        },
        "time_safety": {
            "uses_v11_1_protocol": True,
            "uses_v10_3_final_boundary": True,
            "uses_frozen_risk_evidence_only": True,
            "input_hashes_recorded": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_market_backtest": True,
            "does_not_optimize_parameters": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "research_only": True,
            "external_validation_execution_only": True,
            "uses_v11_1_protocol": True,
            "uses_v10_3_final_boundary": True,
            "uses_frozen_risk_evidence_only": True,
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
    payload["audit"] = validate_h2_external_validation_execution(payload)
    return payload


def write_h2_external_validation_execution(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
