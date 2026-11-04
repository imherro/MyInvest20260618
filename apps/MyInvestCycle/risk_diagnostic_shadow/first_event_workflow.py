from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from implementation_readiness.evidence_package_validator import FORBIDDEN_OUTPUT_KEYS
from risk_diagnostic_shadow.event_quality_audit import (
    BOUNDARY_CHECKS,
    EVENT_INTEGRITY_CHECKS,
    RESEARCH_QUALITY_CHECKS,
)
from risk_diagnostic_shadow.manual_event_capture import DEDUPLICATION_FIELDS, SOURCE_LINEAGE_REQUIRED_FIELDS
from risk_diagnostic_shadow.observation_framework import (
    COMPONENT_ID,
    CONTEXT_SNAPSHOT_FIELDS,
    EVENT_REQUIRED_FIELDS,
    OUTCOME_REVIEW_FIELDS,
)


DEFAULT_OBSERVATION_LOG_PATH = DATA_DIR / "risk_diagnostic_shadow_observation_log.json"
DEFAULT_MANUAL_CAPTURE_PATH = DATA_DIR / "risk_diagnostic_shadow_manual_event_capture.json"
DEFAULT_QUALITY_AUDIT_PATH = DATA_DIR / "risk_diagnostic_shadow_event_quality_audit.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_diagnostic_shadow_first_event_workflow.json"

WORKFLOW_STEPS = [
    "manual_event_json_preparation",
    "schema_validation",
    "source_hash_validation",
    "duplicate_check",
    "no_trade_check",
    "quality_audit_queue",
    "later_outcome_review_placeholder",
]


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


def _event_count(observation_log: Mapping[str, Any]) -> int:
    log = _mapping(observation_log.get("shadow_observation_log"))
    return len(_sequence(log.get("events")))


def _workflow_step_records() -> list[dict[str, object]]:
    descriptions = {
        "manual_event_json_preparation": "Human prepares one event JSON outside automatic market scanning.",
        "schema_validation": "Validate required event fields and nested context/review fields.",
        "source_hash_validation": "Validate source lineage and sha256 artifact hash.",
        "duplicate_check": "Reject duplicate event id or duplicate event-time/source hash key.",
        "no_trade_check": "Reject any event that enables orders, broker, position or risk-control action.",
        "quality_audit_queue": "Queue the event for no-trade quality audit and manual review.",
        "later_outcome_review_placeholder": "Require later outcome, false warning and missed risk review before promotion.",
    }
    return [
        {
            "step_order": index,
            "step_id": step_id,
            "description": descriptions[step_id],
            "automatic_execution_enabled": False,
            "trade_enabled": False,
            "implementation_ready_after_step": False,
        }
        for index, step_id in enumerate(WORKFLOW_STEPS, start=1)
    ]


def validate_risk_diagnostic_shadow_first_event_workflow(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    source_log = _mapping(payload.get("source_observation_log"))
    source_capture = _mapping(payload.get("source_manual_capture"))
    source_quality = _mapping(payload.get("source_quality_audit"))
    workflow = _mapping(payload.get("first_event_workflow"))
    queue = _mapping(payload.get("quality_audit_queue"))
    guardrails = _mapping(payload.get("no_trade_guardrails"))
    time_safety = _mapping(payload.get("time_safety"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("component_id") != COMPONENT_ID:
        raise AssertionError("component_id must be risk_diagnostic_layer")
    if summary.get("workflow_status") != "ready_for_first_manual_event":
        raise AssertionError("workflow status must be ready_for_first_manual_event")
    if summary.get("event_count") != 0:
        raise AssertionError("first event workflow must not create an event")
    if summary.get("quality_queue_count") != 0:
        raise AssertionError("quality queue must be empty before the first manual event")
    for key in (
        "auto_scan_enabled",
        "auto_event_generation_enabled",
        "auto_decision_enabled",
        "auto_warning_enabled",
        "trade_enabled",
        "position_adjustment_enabled",
        "implementation_ready",
        "investable_output",
        "strategy_output_generated",
        "allocation_output_generated",
        "trade_ready",
    ):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    if source_log.get("source_observation_status") != "active":
        raise AssertionError("source observation log must be active")
    if source_log.get("source_event_count") != 0:
        raise AssertionError("source event count must be zero")
    if source_log.get("source_trade_enabled") is not False:
        raise AssertionError("source trade must remain disabled")
    if source_capture.get("source_manual_capture_status") != "ready_for_manual_input":
        raise AssertionError("manual capture source must be ready")
    if source_capture.get("source_trade_enabled") is not False:
        raise AssertionError("manual capture source trade must remain disabled")
    if source_quality.get("source_quality_audit_status") != "no_events_available":
        raise AssertionError("quality source must have no events")
    if source_quality.get("source_trade_enabled") is not False:
        raise AssertionError("quality source trade must remain disabled")

    if workflow.get("workflow_step_count") != len(WORKFLOW_STEPS):
        raise AssertionError("workflow step count mismatch")
    step_ids = [str(item.get("step_id")) for item in _sequence(workflow.get("workflow_steps")) if isinstance(item, Mapping)]
    if step_ids != WORKFLOW_STEPS:
        raise AssertionError("workflow steps mismatch")
    if workflow.get("manual_event_required") is not True:
        raise AssertionError("manual event must be required")
    if workflow.get("auto_event_allowed") is not False:
        raise AssertionError("auto event must be disabled")
    if workflow.get("manual_review_required") is not True:
        raise AssertionError("manual review must be required")

    if queue.get("queue_status") != "empty_waiting_for_first_manual_event":
        raise AssertionError("quality queue must be empty")
    if queue.get("queued_event_count") != 0:
        raise AssertionError("queued event count must be zero")
    if queue.get("automatic_queue_population_enabled") is not False:
        raise AssertionError("automatic queue population must be disabled")

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
    if time_safety.get("does_not_auto_generate_event") is not True:
        raise AssertionError("must not auto generate event")
    if time_safety.get("does_not_auto_judge_risk") is not True:
        raise AssertionError("must not auto judge risk")

    required_constraints = [
        "first_event_workflow_only",
        "ready_for_first_manual_event",
        "no_event_created",
        "manual_event_required",
        "manual_review_required",
        "quality_audit_required",
        "does_not_auto_scan_market",
        "does_not_auto_generate_event",
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
        "checked_workflow_status": summary.get("workflow_status"),
        "checked_event_count": summary.get("event_count"),
        "checked_quality_queue_count": summary.get("quality_queue_count"),
        "checked_trade_enabled": summary.get("trade_enabled"),
        "checked_implementation_ready": summary.get("implementation_ready"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_risk_diagnostic_shadow_first_event_workflow(
    *,
    observation_log_path: str | Path = DEFAULT_OBSERVATION_LOG_PATH,
    manual_capture_path: str | Path = DEFAULT_MANUAL_CAPTURE_PATH,
    quality_audit_path: str | Path = DEFAULT_QUALITY_AUDIT_PATH,
) -> dict[str, object]:
    observation_log = _read_json(observation_log_path)
    manual_capture = _read_json(manual_capture_path)
    quality_audit = _read_json(quality_audit_path)
    if not observation_log or not manual_capture or not quality_audit:
        raise RuntimeError("V14.7 inputs missing; rebuild V14.3, V14.5 and V14.6 artifacts first.")

    log_summary = _mapping(observation_log.get("summary"))
    capture_summary = _mapping(manual_capture.get("summary"))
    quality_summary = _mapping(quality_audit.get("summary"))
    if log_summary.get("component_id") != COMPONENT_ID:
        raise RuntimeError("V14.3 observation log component mismatch.")
    if log_summary.get("observation_status") != "active":
        raise RuntimeError("V14.3 observation log must be active before V14.7.")
    if log_summary.get("trade_enabled") is not False:
        raise RuntimeError("V14.3 trade guardrail must remain disabled.")
    if capture_summary.get("manual_capture_status") != "ready_for_manual_input":
        raise RuntimeError("V14.5 manual capture must be ready before V14.7.")
    if capture_summary.get("trade_enabled") is not False:
        raise RuntimeError("V14.5 trade guardrail must remain disabled.")
    if quality_summary.get("quality_audit_status") != "no_events_available":
        raise RuntimeError("V14.6 quality audit must have no events before the first event workflow.")
    if quality_summary.get("trade_enabled") is not False:
        raise RuntimeError("V14.6 trade guardrail must remain disabled.")

    event_count = _event_count(observation_log)
    if event_count != 0:
        raise RuntimeError("V14.7 first event workflow expects zero current events.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = _mapping(observation_log.get("metadata")).get("as_of")
    input_paths = {
        "v14_3_observation_log": observation_log_path,
        "v14_5_manual_capture": manual_capture_path,
        "v14_6_quality_audit": quality_audit_path,
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V14.7 Risk Diagnostic Shadow Observation First Event Workflow",
            "generated_at": generated_at,
            "as_of": as_of,
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Define the first manual shadow event workflow without automatically creating events, scanning markets, judging risk or trading.",
        },
        "summary": {
            "component_id": COMPONENT_ID,
            "workflow_status": "ready_for_first_manual_event",
            "event_count": 0,
            "quality_queue_count": 0,
            "auto_scan_enabled": False,
            "auto_event_generation_enabled": False,
            "auto_decision_enabled": False,
            "auto_warning_enabled": False,
            "trade_enabled": False,
            "position_adjustment_enabled": False,
            "implementation_gate_result": "blocked",
            "implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "risk_diagnostic_shadow_first_event_workflow_ready_no_event_no_trade",
            "key_read": "V14.7 defines the human workflow for the first shadow event; no event is created in this run.",
        },
        "source_observation_log": {
            "source_observation_status": log_summary.get("observation_status"),
            "source_log_status": log_summary.get("log_status"),
            "source_event_count": event_count,
            "source_auto_trigger_enabled": log_summary.get("auto_trigger_enabled"),
            "source_trade_enabled": log_summary.get("trade_enabled"),
            "source_hash": _file_hash(observation_log_path),
        },
        "source_manual_capture": {
            "source_manual_capture_status": capture_summary.get("manual_capture_status"),
            "source_submitted_event_count": capture_summary.get("submitted_event_count"),
            "source_trade_enabled": capture_summary.get("trade_enabled"),
            "source_hash": _file_hash(manual_capture_path),
        },
        "source_quality_audit": {
            "source_quality_audit_status": quality_summary.get("quality_audit_status"),
            "source_quality_checked_events": quality_summary.get("quality_checked_events"),
            "source_trade_enabled": quality_summary.get("trade_enabled"),
            "source_hash": _file_hash(quality_audit_path),
        },
        "first_event_workflow": {
            "workflow_step_count": len(WORKFLOW_STEPS),
            "workflow_steps": _workflow_step_records(),
            "manual_event_required": True,
            "auto_event_allowed": False,
            "manual_review_required": True,
            "workflow_note": "The workflow starts only after a human supplies a no-trade event JSON.",
        },
        "first_event_input_requirements": {
            "event_required_fields": EVENT_REQUIRED_FIELDS,
            "context_snapshot_required_fields": CONTEXT_SNAPSHOT_FIELDS,
            "source_lineage_required_fields": SOURCE_LINEAGE_REQUIRED_FIELDS,
            "later_outcome_review_required_fields": OUTCOME_REVIEW_FIELDS,
            "dedupe_key_fields": DEDUPLICATION_FIELDS,
            "event_integrity_checks": EVENT_INTEGRITY_CHECKS,
            "research_quality_checks": RESEARCH_QUALITY_CHECKS,
            "boundary_checks": BOUNDARY_CHECKS,
        },
        "quality_audit_queue": {
            "queue_status": "empty_waiting_for_first_manual_event",
            "queued_event_count": 0,
            "automatic_queue_population_enabled": False,
            "next_allowed_input": "human_supplied_no_trade_event_json",
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
            "blocking_reasons": [
                "first_manual_event_not_submitted",
                "quality_audit_queue_empty",
                "later_outcome_review_missing",
                "manual_review_not_approved",
                "workflow_only",
            ],
        },
        "time_safety": {
            "uses_v14_3_v14_5_v14_6_artifacts_only": True,
            "input_hashes_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_scan_market": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_auto_generate_event": True,
            "does_not_auto_generate_warning": True,
            "does_not_auto_judge_risk": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "first_event_workflow_only": True,
            "ready_for_first_manual_event": True,
            "no_event_created": True,
            "manual_event_required": True,
            "manual_review_required": True,
            "quality_audit_required": True,
            "does_not_auto_scan_market": True,
            "does_not_auto_generate_event": True,
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
    payload["audit"] = validate_risk_diagnostic_shadow_first_event_workflow(payload)
    return payload


def write_risk_diagnostic_shadow_first_event_workflow(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
