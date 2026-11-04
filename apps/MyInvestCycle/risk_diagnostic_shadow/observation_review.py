from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from implementation_readiness.evidence_package_validator import FORBIDDEN_OUTPUT_KEYS
from risk_diagnostic_shadow.observation_framework import COMPONENT_ID


DEFAULT_OBSERVATION_LOG_PATH = DATA_DIR / "risk_diagnostic_shadow_observation_log.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_diagnostic_shadow_observation_review.json"

REVIEW_CHECKS = [
    "event_completeness",
    "source_lineage",
    "no_trade_compliance",
    "later_outcome_review_completeness",
    "false_warning_review",
    "missed_risk_review",
]
ALLOWED_REVIEW_STATUSES = {"no_events_available", "events_pending_manual_review"}
ALLOWED_SOURCE_LOG_STATUSES = {"active_empty", "active_with_manual_events"}


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


def validate_risk_diagnostic_shadow_observation_review(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    source = _mapping(payload.get("source_observation_log"))
    review_framework = _mapping(payload.get("review_framework"))
    review_result = _mapping(payload.get("review_result"))
    guardrails = _mapping(payload.get("no_trade_guardrails"))
    time_safety = _mapping(payload.get("time_safety"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("component_id") != COMPONENT_ID:
        raise AssertionError("component_id must be risk_diagnostic_layer")
    if summary.get("review_framework_status") != "defined":
        raise AssertionError("review framework must be defined")
    if summary.get("review_status") not in ALLOWED_REVIEW_STATUSES:
        raise AssertionError("review status must be no_events_available or events_pending_manual_review")
    if summary.get("reviewed_event_count") != 0:
        raise AssertionError("reviewed event count must be zero")
    event_count = int(summary.get("event_count") or 0)
    if event_count < 0:
        raise AssertionError("event count cannot be negative")
    if summary.get("auto_review_enabled") is not False:
        raise AssertionError("auto review must be disabled")
    if summary.get("auto_warning_enabled") is not False:
        raise AssertionError("auto warning must be disabled")
    if summary.get("trade_enabled") is not False:
        raise AssertionError("trade must be disabled")
    if summary.get("implementation_ready") is not False:
        raise AssertionError("implementation_ready must be false")
    if summary.get("investable_output") is not False:
        raise AssertionError("investable output must be false")
    if summary.get("strategy_output_generated") is not False:
        raise AssertionError("strategy output must be false")
    if summary.get("allocation_output_generated") is not False:
        raise AssertionError("allocation output must be false")
    if summary.get("trade_ready") is not False:
        raise AssertionError("trade_ready must be false")
    allowed_conclusions = {
        "risk_diagnostic_shadow_review_no_events_no_trade",
        "risk_diagnostic_shadow_events_pending_manual_review_no_trade",
    }
    if summary.get("conclusion") not in allowed_conclusions:
        raise AssertionError("unexpected conclusion")

    if source.get("source_observation_status") != "active":
        raise AssertionError("source observation log must be active")
    if source.get("source_log_status") not in ALLOWED_SOURCE_LOG_STATUSES:
        raise AssertionError("source log must be active empty or active with manual events")
    if int(source.get("source_event_count") or 0) != event_count:
        raise AssertionError("source event count mismatch")

    if set(_sequence(review_framework.get("review_checks"))) != set(REVIEW_CHECKS):
        raise AssertionError("review checks mismatch")
    if review_framework.get("manual_review_required") is not True:
        raise AssertionError("manual review must be required")
    if review_framework.get("auto_decision_allowed") is not False:
        raise AssertionError("auto decision must be disabled")

    if review_result.get("review_status") != summary.get("review_status"):
        raise AssertionError("review result status mismatch")
    if review_result.get("reviewed_event_count") != 0:
        raise AssertionError("review result count must be zero")
    if _sequence(review_result.get("event_reviews")):
        raise AssertionError("event reviews must be empty")

    for key in (
        "trade_enabled",
        "order_generation_enabled",
        "broker_connection_enabled",
        "position_adjustment_enabled",
        "auto_risk_control_enabled",
    ):
        if guardrails.get(key) is not False:
            raise AssertionError(f"guardrails.{key} must be false")

    if time_safety.get("does_not_read_market_price_data") is not True:
        raise AssertionError("must not read market price data")
    if time_safety.get("does_not_auto_generate_warning") is not True:
        raise AssertionError("must not auto generate warning")
    if time_safety.get("does_not_auto_review_events") is not True:
        raise AssertionError("must not auto review events")

    required_constraints = [
        "review_framework_only",
        "does_not_auto_generate_warning",
        "does_not_auto_judge_risk",
        "does_not_enable_auto_risk_control",
        "does_not_adjust_position",
        "does_not_adjust_exposure",
        "does_not_generate_strategy",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_generate_portfolio_weight",
        "does_not_generate_allocation",
        "does_not_optimize_parameters",
        "does_not_generate_trade_signal",
        "no_order_generation",
        "no_broker_connection",
    ]
    if event_count == 0:
        if constraints.get("no_events_available") is not True:
            raise AssertionError("constraints.no_events_available must be true when event count is zero")
    else:
        if constraints.get("events_pending_manual_review") is not True:
            raise AssertionError("constraints.events_pending_manual_review must be true when events exist")
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(
        key for key in _walk_keys(payload) if key != "forbidden_outputs"
    )
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_component_id": summary.get("component_id"),
        "checked_review_status": summary.get("review_status"),
        "checked_reviewed_event_count": summary.get("reviewed_event_count"),
        "checked_trade_enabled": summary.get("trade_enabled"),
        "checked_implementation_ready": summary.get("implementation_ready"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_risk_diagnostic_shadow_observation_review(
    *,
    observation_log_path: str | Path = DEFAULT_OBSERVATION_LOG_PATH,
) -> dict[str, object]:
    observation_log = _read_json(observation_log_path)
    if not observation_log:
        raise RuntimeError("V14.4 input missing; rebuild V14.3 shadow observation log first.")
    log_summary = _mapping(observation_log.get("summary"))
    if log_summary.get("component_id") != COMPONENT_ID:
        raise RuntimeError("V14.3 observation log component mismatch.")
    if log_summary.get("observation_status") != "active":
        raise RuntimeError("V14.3 observation log must be active before V14.4.")
    if log_summary.get("trade_enabled") is not False:
        raise RuntimeError("V14.3 trade guardrail must remain disabled.")

    event_count = int(log_summary.get("event_count") or 0)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = _mapping(observation_log.get("metadata")).get("as_of")
    input_paths = {"v14_3_observation_log": observation_log_path}
    review_status = "no_events_available" if event_count == 0 else "events_pending_manual_review"
    result_note = (
        "No shadow events are available to review yet."
        if event_count == 0
        else "Manual shadow events exist, but no automatic event review is generated."
    )
    key_read = (
        "V14.4 defines how future no-trade shadow events will be reviewed; current log has no events, so no event review exists."
        if event_count == 0
        else "V14.4 detects manually logged no-trade shadow events but leaves them pending manual review."
    )
    blocking_reasons = [
        "no_shadow_events_available",
        "no_later_outcome_review_yet",
        "manual_review_not_approved",
        "review_framework_only",
    ] if event_count == 0 else [
        "shadow_events_pending_manual_review",
        "no_later_outcome_review_yet",
        "manual_review_not_approved",
        "review_framework_only",
    ]
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V14.4 Risk Diagnostic Shadow Observation Event Review Framework",
            "generated_at": generated_at,
            "as_of": as_of,
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Define the review framework for future no-trade shadow events without generating warnings, judging risk automatically or trading.",
        },
        "summary": {
            "component_id": COMPONENT_ID,
            "review_framework_status": "defined",
            "review_status": review_status,
            "event_count": event_count,
            "reviewed_event_count": 0,
            "auto_review_enabled": False,
            "auto_warning_enabled": False,
            "trade_enabled": False,
            "position_adjustment_enabled": False,
            "implementation_gate_result": "blocked",
            "implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "risk_diagnostic_shadow_review_no_events_no_trade"
            if event_count == 0
            else "risk_diagnostic_shadow_events_pending_manual_review_no_trade",
            "key_read": key_read,
        },
        "source_observation_log": {
            "source_observation_status": log_summary.get("observation_status"),
            "source_log_status": log_summary.get("log_status"),
            "source_event_count": log_summary.get("event_count"),
            "source_auto_trigger_enabled": log_summary.get("auto_trigger_enabled"),
            "source_trade_enabled": log_summary.get("trade_enabled"),
            "source_hash": _file_hash(observation_log_path),
        },
        "review_framework": {
            "review_checks": REVIEW_CHECKS,
            "manual_review_required": True,
            "auto_decision_allowed": False,
            "requires_later_outcome_review": True,
            "requires_false_warning_review": True,
            "requires_missed_risk_review": True,
            "requires_source_lineage": True,
            "framework_note": "Future event reviews must be manual evidence records, not automatic risk decisions.",
        },
        "review_result": {
            "review_status": review_status,
            "reviewed_event_count": 0,
            "event_reviews": [],
            "result_note": result_note,
        },
        "no_trade_guardrails": {
            "trade_enabled": False,
            "order_generation_enabled": False,
            "broker_connection_enabled": False,
            "position_adjustment_enabled": False,
            "auto_risk_control_enabled": False,
        },
        "promotion_gate": {
            "promotion_allowed": False,
            "implementation_ready": False,
            "blocking_reasons": blocking_reasons,
        },
        "time_safety": {
            "uses_v14_3_observation_log_only": True,
            "input_hashes_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_auto_generate_warning": True,
            "does_not_auto_review_events": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "review_framework_only": True,
            "no_events_available": event_count == 0,
            "events_pending_manual_review": event_count > 0,
            "does_not_auto_generate_warning": True,
            "does_not_auto_judge_risk": True,
            "does_not_enable_auto_risk_control": True,
            "does_not_adjust_position": True,
            "does_not_adjust_exposure": True,
            "does_not_generate_strategy": True,
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
    payload["audit"] = validate_risk_diagnostic_shadow_observation_review(payload)
    return payload


def write_risk_diagnostic_shadow_observation_review(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
