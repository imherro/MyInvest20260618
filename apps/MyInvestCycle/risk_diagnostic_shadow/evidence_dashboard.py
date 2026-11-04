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
DEFAULT_MANUAL_CAPTURE_PATH = DATA_DIR / "risk_diagnostic_shadow_manual_event_capture.json"
DEFAULT_OBSERVATION_REVIEW_PATH = DATA_DIR / "risk_diagnostic_shadow_observation_review.json"
DEFAULT_QUALITY_AUDIT_PATH = DATA_DIR / "risk_diagnostic_shadow_event_quality_audit.json"
DEFAULT_FIRST_EVENT_WORKFLOW_PATH = DATA_DIR / "risk_diagnostic_shadow_first_event_workflow.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_diagnostic_shadow_evidence_dashboard.json"


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


def _event_count_from_log(observation_log: Mapping[str, Any]) -> int:
    log = _mapping(observation_log.get("shadow_observation_log"))
    events = _sequence(log.get("events"))
    if isinstance(log.get("event_count"), int):
        return int(log.get("event_count") or 0)
    return len(events)


def _false_warning_count(review_payload: Mapping[str, Any]) -> int:
    result = _mapping(review_payload.get("review_result"))
    reviews = _sequence(result.get("event_reviews"))
    count = 0
    for item in reviews:
        if not isinstance(item, Mapping):
            continue
        later = _mapping(item.get("later_outcome_review"))
        value = later.get("false_warning_review", item.get("false_warning_review"))
        if value is True or value == "true" or value == "confirmed":
            count += 1
    return count


def _missed_risk_count(review_payload: Mapping[str, Any]) -> int:
    result = _mapping(review_payload.get("review_result"))
    reviews = _sequence(result.get("event_reviews"))
    count = 0
    for item in reviews:
        if not isinstance(item, Mapping):
            continue
        later = _mapping(item.get("later_outcome_review"))
        value = later.get("missed_risk_review", item.get("missed_risk_review"))
        if value is True or value == "true" or value == "confirmed":
            count += 1
    return count


def validate_risk_diagnostic_shadow_evidence_dashboard(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    statistics = _mapping(payload.get("event_statistics"))
    status = _mapping(payload.get("evidence_status"))
    gate = _mapping(payload.get("implementation_gate"))
    guardrails = _mapping(payload.get("no_trade_guardrails"))
    time_safety = _mapping(payload.get("time_safety"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("component_id") != COMPONENT_ID:
        raise AssertionError("component_id must be risk_diagnostic_layer")
    if summary.get("dashboard_status") != "ready":
        raise AssertionError("dashboard status must be ready")
    if summary.get("dashboard_only") is not True:
        raise AssertionError("dashboard_only must be true")
    if summary.get("implementation_ready") is not False:
        raise AssertionError("implementation_ready must be false")
    if summary.get("trade_enabled") is not False:
        raise AssertionError("trade must be disabled")

    required_stat_keys = [
        "event_count",
        "validated_event_count",
        "pending_review_count",
        "reviewed_count",
        "false_warning_count",
        "missed_risk_count",
        "quality_queue_count",
    ]
    for key in required_stat_keys:
        if not isinstance(statistics.get(key), int) or int(statistics.get(key) or 0) < 0:
            raise AssertionError(f"event_statistics.{key} must be a non-negative integer")
    if statistics.get("event_count") != 0:
        raise AssertionError("V14.9 current dashboard must show zero events")
    if statistics.get("validated_event_count") != 0:
        raise AssertionError("V14.9 current dashboard must show zero validated events")
    if statistics.get("quality_queue_count") != 0:
        raise AssertionError("V14.9 current dashboard must show zero quality queue items")

    if status.get("shadow_status") != "active_empty":
        raise AssertionError("shadow status must remain active_empty")
    if status.get("evidence_accumulation_status") != "waiting_for_manual_events":
        raise AssertionError("evidence status must wait for manual events")
    if gate.get("implementation_ready") is not False:
        raise AssertionError("implementation gate must remain blocked")
    if gate.get("trade_enabled") is not False:
        raise AssertionError("implementation gate trade must be disabled")

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
    if time_safety.get("does_not_scan_market") is not True:
        raise AssertionError("must not scan market")
    if time_safety.get("does_not_generate_event") is not True:
        raise AssertionError("must not generate event")
    if time_safety.get("does_not_judge_risk") is not True:
        raise AssertionError("must not judge risk")

    required_constraints = [
        "dashboard_only",
        "does_not_generate_event",
        "does_not_scan_market",
        "does_not_judge_risk",
        "does_not_adjust_exposure",
        "does_not_generate_strategy",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_generate_portfolio_weight",
        "does_not_generate_allocation",
        "does_not_allocate",
        "does_not_trade",
        "no_order_generation",
        "no_broker_connection",
    ]
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
        "checked_dashboard_status": summary.get("dashboard_status"),
        "checked_event_count": statistics.get("event_count"),
        "checked_validated_event_count": statistics.get("validated_event_count"),
        "checked_quality_queue_count": statistics.get("quality_queue_count"),
        "checked_trade_enabled": gate.get("trade_enabled"),
        "checked_implementation_ready": gate.get("implementation_ready"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_risk_diagnostic_shadow_evidence_dashboard(
    *,
    observation_log_path: str | Path = DEFAULT_OBSERVATION_LOG_PATH,
    manual_capture_path: str | Path = DEFAULT_MANUAL_CAPTURE_PATH,
    observation_review_path: str | Path = DEFAULT_OBSERVATION_REVIEW_PATH,
    quality_audit_path: str | Path = DEFAULT_QUALITY_AUDIT_PATH,
    first_event_workflow_path: str | Path = DEFAULT_FIRST_EVENT_WORKFLOW_PATH,
) -> dict[str, object]:
    observation_log = _read_json(observation_log_path)
    manual_capture = _read_json(manual_capture_path)
    observation_review = _read_json(observation_review_path)
    quality_audit = _read_json(quality_audit_path)
    first_event_workflow = _read_json(first_event_workflow_path)
    if not all((observation_log, manual_capture, observation_review, quality_audit, first_event_workflow)):
        raise RuntimeError("V14.9 inputs missing; rebuild V14.3, V14.4, V14.5, V14.6 and V14.7 artifacts first.")

    log_summary = _mapping(observation_log.get("summary"))
    capture_summary = _mapping(manual_capture.get("summary"))
    review_summary = _mapping(observation_review.get("summary"))
    quality_summary = _mapping(quality_audit.get("summary"))
    workflow_summary = _mapping(first_event_workflow.get("summary"))
    for name, summary in {
        "observation_log": log_summary,
        "manual_capture": capture_summary,
        "observation_review": review_summary,
        "quality_audit": quality_summary,
        "first_event_workflow": workflow_summary,
    }.items():
        if summary.get("component_id") != COMPONENT_ID:
            raise RuntimeError(f"{name} component mismatch.")
        if summary.get("trade_enabled") is not False:
            raise RuntimeError(f"{name} trade guardrail must remain disabled.")

    event_count = _event_count_from_log(observation_log)
    reviewed_count = int(review_summary.get("reviewed_event_count") or 0)
    quality_queue_count = int(workflow_summary.get("quality_queue_count") or 0)
    statistics = {
        "event_count": event_count,
        "validated_event_count": 0,
        "pending_review_count": max(event_count - reviewed_count, 0),
        "reviewed_count": reviewed_count,
        "false_warning_count": _false_warning_count(observation_review),
        "missed_risk_count": _missed_risk_count(observation_review),
        "quality_queue_count": quality_queue_count,
    }
    evidence_accumulation_status = "waiting_for_manual_events" if event_count == 0 else "manual_events_pending_review"
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = _mapping(observation_log.get("metadata")).get("as_of")
    input_paths = {
        "v14_3_observation_log": observation_log_path,
        "v14_5_manual_capture": manual_capture_path,
        "v14_4_observation_review": observation_review_path,
        "v14_6_quality_audit": quality_audit_path,
        "v14_7_first_event_workflow": first_event_workflow_path,
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V14.9 Risk Diagnostic Shadow Evidence Accumulation Dashboard",
            "generated_at": generated_at,
            "as_of": as_of,
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Display shadow evidence accumulation status without creating events, scanning markets, judging risk or trading.",
        },
        "summary": {
            "component_id": COMPONENT_ID,
            "dashboard_status": "ready",
            "dashboard_only": True,
            "evidence_accumulation_status": evidence_accumulation_status,
            "event_count": event_count,
            "implementation_gate_result": "blocked",
            "implementation_ready": False,
            "trade_enabled": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "risk_diagnostic_shadow_evidence_dashboard_waiting_for_manual_events_no_trade",
            "key_read": "V14.9 displays the risk diagnostic shadow evidence backlog; no evidence event has been submitted.",
        },
        "event_statistics": statistics,
        "evidence_status": {
            "shadow_status": log_summary.get("log_status"),
            "manual_capture_status": capture_summary.get("manual_capture_status"),
            "review_status": review_summary.get("review_status"),
            "quality_audit_status": quality_summary.get("quality_audit_status"),
            "first_event_workflow_status": workflow_summary.get("workflow_status"),
            "evidence_accumulation_status": evidence_accumulation_status,
        },
        "implementation_gate": {
            "implementation_ready": False,
            "trade_enabled": False,
            "blocking_reasons": [
                "no_shadow_events_available",
                "first_manual_event_not_submitted",
                "manual_review_not_approved",
                "dashboard_only",
            ],
        },
        "no_trade_guardrails": {
            "trade_enabled": False,
            "order_generation_enabled": False,
            "broker_connection_enabled": False,
            "position_adjustment_enabled": False,
            "auto_risk_control_enabled": False,
        },
        "time_safety": {
            "uses_existing_shadow_artifacts_only": True,
            "input_hashes_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_scan_market": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_generate_event": True,
            "does_not_generate_warning": True,
            "does_not_judge_risk": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "dashboard_only": True,
            "does_not_generate_event": True,
            "does_not_scan_market": True,
            "does_not_judge_risk": True,
            "does_not_adjust_exposure": True,
            "does_not_generate_strategy": True,
            "does_not_select_assets": True,
            "does_not_map_etf": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_allocation": True,
            "does_not_allocate": True,
            "does_not_trade": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
        "forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }
    payload["audit"] = validate_risk_diagnostic_shadow_evidence_dashboard(payload)
    return payload


def write_risk_diagnostic_shadow_evidence_dashboard(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
