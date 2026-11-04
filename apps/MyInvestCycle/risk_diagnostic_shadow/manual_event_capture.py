from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from implementation_readiness.evidence_package_validator import FORBIDDEN_OUTPUT_KEYS
from risk_diagnostic_shadow.observation_framework import (
    COMPONENT_ID,
    CONTEXT_SNAPSHOT_FIELDS,
    EVENT_REQUIRED_FIELDS,
    OUTCOME_REVIEW_FIELDS,
)
from risk_diagnostic_shadow.observation_logger import append_no_trade_observation_event


DEFAULT_OBSERVATION_LOG_PATH = DATA_DIR / "risk_diagnostic_shadow_observation_log.json"
DEFAULT_CAPTURE_STATUS_PATH = DATA_DIR / "risk_diagnostic_shadow_manual_event_capture.json"

SOURCE_LINEAGE_REQUIRED_FIELDS = [
    "source_artifact_hash",
    "event_schema_version",
    "created_by",
]
DEDUPLICATION_FIELDS = [
    "event_time",
    "market_data_as_of",
    "warning_event_type",
    "source_artifact_hash",
]
ALLOWED_MANUAL_REVIEW_STATES = {
    "submitted_pending_later_outcome_review",
    "submitted_pending_manual_review",
    "manual_review_in_progress",
    "manual_review_rejected",
    "manual_review_approved_observation_only",
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


def _dedupe_tuple(event: Mapping[str, Any]) -> tuple[str, str, str, str]:
    source_lineage = _mapping(event.get("source_lineage"))
    return (
        str(event.get("event_time") or ""),
        str(event.get("market_data_as_of") or ""),
        str(event.get("warning_event_type") or ""),
        str(source_lineage.get("source_artifact_hash") or ""),
    )


def _event_count(log_payload: Mapping[str, Any]) -> int:
    summary = _mapping(log_payload.get("summary"))
    if isinstance(summary.get("event_count"), int):
        return int(summary.get("event_count") or 0)
    log = _mapping(log_payload.get("shadow_observation_log"))
    return len(_sequence(log.get("events")))


def _validate_hash(value: object, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in value):
        raise ValueError(f"{field_name} must be a 64-character sha256 hex hash")


def _validate_mapping_fields(container: Mapping[str, Any], fields: Sequence[str], label: str) -> None:
    missing = [field for field in fields if field not in container]
    if missing:
        raise ValueError(f"missing {label} fields: {missing}")


def _existing_events(log_payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    log = _mapping(log_payload.get("shadow_observation_log"))
    return [event for event in _sequence(log.get("events")) if isinstance(event, Mapping)]


def _assert_no_forbidden_outputs(payload: Mapping[str, Any]) -> None:
    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(
        key for key in _walk_keys(payload) if key != "forbidden_outputs"
    )
    if disallowed_payload_keys:
        raise ValueError(f"forbidden output keys found: {sorted(disallowed_payload_keys)}")


def validate_manual_shadow_event(log_payload: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, object]:
    summary = _mapping(log_payload.get("summary"))
    controls = _mapping(log_payload.get("observation_controls"))
    if summary.get("component_id") != COMPONENT_ID:
        raise ValueError("observation log component_id mismatch")
    if summary.get("observation_status") != "active":
        raise ValueError("observation log must be active")
    if summary.get("manual_append_only") is not True:
        raise ValueError("observation log must be manual append only")
    if summary.get("auto_trigger_enabled") is not False:
        raise ValueError("automatic trigger must remain disabled")
    if summary.get("trade_enabled") is not False:
        raise ValueError("observation log trade guardrail must remain disabled")
    if controls.get("append_mode") != "manual_only":
        raise ValueError("append mode must be manual_only")

    missing = [field for field in EVENT_REQUIRED_FIELDS if field not in event]
    if missing:
        raise ValueError(f"missing event fields: {missing}")
    if event.get("component_id") != COMPONENT_ID:
        raise ValueError("event component_id mismatch")

    context_snapshot = _mapping(event.get("context_snapshot"))
    source_lineage = _mapping(event.get("source_lineage"))
    later_outcome_review = _mapping(event.get("later_outcome_review"))
    no_trade_observation = _mapping(event.get("no_trade_observation"))

    _validate_mapping_fields(context_snapshot, CONTEXT_SNAPSHOT_FIELDS, "context_snapshot")
    _validate_mapping_fields(source_lineage, SOURCE_LINEAGE_REQUIRED_FIELDS, "source_lineage")
    _validate_mapping_fields(later_outcome_review, OUTCOME_REVIEW_FIELDS, "later_outcome_review")
    _validate_hash(source_lineage.get("source_artifact_hash"), "source_lineage.source_artifact_hash")

    if event.get("manual_review_state") not in ALLOWED_MANUAL_REVIEW_STATES:
        raise ValueError("manual_review_state is not an allowed manual state")
    if not all(
        no_trade_observation.get(key) is False
        for key in (
            "trade_enabled",
            "order_generation_enabled",
            "broker_connection_enabled",
            "position_adjustment_enabled",
        )
    ):
        raise ValueError("event does not satisfy no-trade guardrails")

    event_id = str(event.get("event_id") or "")
    if not event_id:
        raise ValueError("event_id is required")
    if any(str(existing.get("event_id") or "") == event_id for existing in _existing_events(log_payload)):
        raise ValueError(f"duplicate event_id: {event_id}")

    event_dedupe = _dedupe_tuple(event)
    if any(_dedupe_tuple(existing) == event_dedupe for existing in _existing_events(log_payload)):
        raise ValueError("duplicate manual shadow event detected by dedupe key")

    _assert_no_forbidden_outputs(event)
    return {
        "validation_status": "passed",
        "component_id": event.get("component_id"),
        "event_id": event_id,
        "dedupe_key": dict(zip(DEDUPLICATION_FIELDS, event_dedupe, strict=True)),
        "trade_enabled": False,
        "auto_warning_generated": False,
        "implementation_ready": False,
    }


def append_manual_shadow_event(
    log_payload: Mapping[str, Any],
    event: Mapping[str, Any],
) -> dict[str, object]:
    validation = validate_manual_shadow_event(log_payload, event)
    updated = append_no_trade_observation_event(log_payload, event)

    updated_payload = deepcopy(updated)
    event_count = _event_count(updated_payload)
    log = dict(_mapping(updated_payload.get("shadow_observation_log")))
    summary = dict(_mapping(updated_payload.get("summary")))
    promotion = dict(_mapping(updated_payload.get("promotion_gate")))

    log["log_status"] = "active_with_manual_events"
    log["event_count"] = event_count
    log["live_event_count"] = event_count
    summary["log_status"] = "active_with_manual_events"
    summary["event_count"] = event_count
    summary["live_event_count"] = event_count
    summary["implementation_gate_result"] = "blocked"
    summary["implementation_ready"] = False
    summary["investable_output"] = False
    summary["strategy_output_generated"] = False
    summary["allocation_output_generated"] = False
    summary["trade_ready"] = False
    summary["conclusion"] = "risk_diagnostic_shadow_manual_event_logged_no_trade"
    promotion["promotion_allowed"] = False
    promotion["implementation_ready"] = False
    promotion["blocking_reasons"] = [
        "manual_event_pending_later_outcome_review",
        "manual_review_not_approved_for_implementation",
        "log_records_observation_only",
    ]

    updated_payload["summary"] = summary
    updated_payload["shadow_observation_log"] = log
    updated_payload["promotion_gate"] = promotion
    updated_payload["manual_capture_validation"] = validation
    return updated_payload


def validate_risk_diagnostic_shadow_manual_event_capture(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    controls = _mapping(payload.get("manual_capture_controls"))
    source = _mapping(payload.get("source_observation_log"))
    guardrails = _mapping(payload.get("no_trade_guardrails"))
    time_safety = _mapping(payload.get("time_safety"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("component_id") != COMPONENT_ID:
        raise AssertionError("component_id must be risk_diagnostic_layer")
    if summary.get("manual_capture_status") != "ready_for_manual_input":
        raise AssertionError("manual capture must be ready_for_manual_input")
    submitted_event_count = int(summary.get("submitted_event_count") or 0)
    if submitted_event_count < 0:
        raise AssertionError("submitted event count cannot be negative")
    if summary.get("auto_trigger_enabled") is not False:
        raise AssertionError("auto trigger must be disabled")
    if summary.get("auto_warning_enabled") is not False:
        raise AssertionError("auto warning must be disabled")
    if summary.get("trade_enabled") is not False:
        raise AssertionError("trade must be disabled")
    if summary.get("position_adjustment_enabled") is not False:
        raise AssertionError("position adjustment must be disabled")
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

    if controls.get("append_mode") != "manual_event_file_only":
        raise AssertionError("append mode must require a manual event file")
    if controls.get("duplicate_detection_enabled") is not True:
        raise AssertionError("duplicate detection must be enabled")
    if controls.get("auto_event_generation_enabled") is not False:
        raise AssertionError("auto event generation must be disabled")
    if controls.get("manual_review_required") is not True:
        raise AssertionError("manual review must be required")

    if source.get("source_observation_status") != "active":
        raise AssertionError("source observation log must be active")
    if source.get("source_trade_enabled") is not False:
        raise AssertionError("source trade must remain disabled")

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
    if time_safety.get("does_not_auto_judge_risk") is not True:
        raise AssertionError("must not auto judge risk")

    required_constraints = [
        "manual_capture_capability_only",
        "manual_append_only",
        "append_only_log",
        "duplicate_detection_enabled",
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
    current_result = _mapping(payload.get("current_capture_result"))
    if submitted_event_count == 0:
        if constraints.get("no_event_submitted_in_status_artifact") is not True:
            raise AssertionError("constraints.no_event_submitted_in_status_artifact must be true when no event is supplied")
        if current_result.get("event_file_supplied") is not False:
            raise AssertionError("current_capture_result.event_file_supplied must be false when submitted count is zero")
    else:
        if constraints.get("manual_event_appended_no_trade") is not True:
            raise AssertionError("constraints.manual_event_appended_no_trade must be true when an event is supplied")
        if current_result.get("event_file_supplied") is not True:
            raise AssertionError("current_capture_result.event_file_supplied must be true when submitted count is positive")
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
        "checked_manual_capture_status": summary.get("manual_capture_status"),
        "checked_source_event_count": source.get("source_event_count"),
        "checked_submitted_event_count": submitted_event_count,
        "checked_trade_enabled": summary.get("trade_enabled"),
        "checked_implementation_ready": summary.get("implementation_ready"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_risk_diagnostic_shadow_manual_event_capture_status(
    *,
    observation_log_path: str | Path = DEFAULT_OBSERVATION_LOG_PATH,
) -> dict[str, object]:
    observation_log = _read_json(observation_log_path)
    if not observation_log:
        raise RuntimeError("V14.5 input missing; rebuild V14.3 shadow observation log first.")
    log_summary = _mapping(observation_log.get("summary"))
    if log_summary.get("component_id") != COMPONENT_ID:
        raise RuntimeError("V14.3 observation log component mismatch.")
    if log_summary.get("observation_status") != "active":
        raise RuntimeError("V14.3 observation log must be active before V14.5.")
    if log_summary.get("trade_enabled") is not False:
        raise RuntimeError("V14.3 trade guardrail must remain disabled.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = _mapping(observation_log.get("metadata")).get("as_of")
    event_count = _event_count(observation_log)
    input_paths = {"v14_3_observation_log": observation_log_path}
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V14.5 Risk Diagnostic Shadow Event Manual Capture",
            "generated_at": generated_at,
            "as_of": as_of,
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Expose a manual append-only no-trade shadow event capture capability without automatically generating warnings or trades.",
        },
        "summary": {
            "component_id": COMPONENT_ID,
            "manual_capture_status": "ready_for_manual_input",
            "source_event_count": event_count,
            "submitted_event_count": 0,
            "auto_trigger_enabled": False,
            "auto_warning_enabled": False,
            "trade_enabled": False,
            "position_adjustment_enabled": False,
            "implementation_gate_result": "blocked",
            "implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "risk_diagnostic_shadow_manual_capture_ready_no_event_no_trade",
            "key_read": "V14.5 enables future manual no-trade event capture; this status artifact submits no event.",
        },
        "source_observation_log": {
            "source_observation_status": log_summary.get("observation_status"),
            "source_log_status": log_summary.get("log_status"),
            "source_event_count": event_count,
            "source_auto_trigger_enabled": log_summary.get("auto_trigger_enabled"),
            "source_trade_enabled": log_summary.get("trade_enabled"),
            "source_hash": _file_hash(observation_log_path),
        },
        "manual_capture_controls": {
            "append_mode": "manual_event_file_only",
            "manual_event_required_fields": EVENT_REQUIRED_FIELDS,
            "source_lineage_required_fields": SOURCE_LINEAGE_REQUIRED_FIELDS,
            "context_snapshot_required_fields": CONTEXT_SNAPSHOT_FIELDS,
            "later_outcome_review_required_fields": OUTCOME_REVIEW_FIELDS,
            "dedupe_key_fields": DEDUPLICATION_FIELDS,
            "allowed_manual_review_states": sorted(ALLOWED_MANUAL_REVIEW_STATES),
            "duplicate_detection_enabled": True,
            "append_only_log": True,
            "manual_review_required": True,
            "auto_event_generation_enabled": False,
            "auto_warning_detection_enabled": False,
            "market_data_reader_enabled": False,
        },
        "current_capture_result": {
            "event_file_supplied": False,
            "submitted_event_count": 0,
            "event_id": None,
            "append_result": "no_event_submitted",
            "result_note": "No manual event file was supplied in this run; observation log is unchanged.",
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
                "manual_event_capture_capability_only",
                "no_event_submitted_in_status_artifact",
                "later_outcome_review_required_after_future_events",
                "manual_review_not_approved",
            ],
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
            "does_not_auto_judge_risk": True,
            "does_not_auto_adjust_risk": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "manual_capture_capability_only": True,
            "no_event_submitted_in_status_artifact": True,
            "manual_append_only": True,
            "append_only_log": True,
            "duplicate_detection_enabled": True,
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
    payload["audit"] = validate_risk_diagnostic_shadow_manual_event_capture(payload)
    return payload


def capture_manual_shadow_event_from_file(
    event_file: str | Path,
    *,
    observation_log_path: str | Path = DEFAULT_OBSERVATION_LOG_PATH,
    capture_status_path: str | Path = DEFAULT_CAPTURE_STATUS_PATH,
) -> dict[str, object]:
    event_path = Path(event_file)
    event = _read_json(event_path)
    if not event:
        raise RuntimeError("manual event file is missing or not a JSON object")
    observation_log = _read_json(observation_log_path)
    if not observation_log:
        raise RuntimeError("observation log missing; rebuild V14.3 first")

    updated_log = append_manual_shadow_event(observation_log, event)
    Path(observation_log_path).write_text(
        json.dumps(updated_log, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    status = build_risk_diagnostic_shadow_manual_event_capture_status(
        observation_log_path=observation_log_path,
    )
    summary = dict(_mapping(status.get("summary")))
    capture_result = dict(_mapping(status.get("current_capture_result")))
    constraints = dict(_mapping(status.get("constraints")))
    summary["submitted_event_count"] = 1
    summary["source_event_count"] = _event_count(updated_log)
    capture_result.update(
        {
            "event_file_supplied": True,
            "submitted_event_count": 1,
            "event_id": event.get("event_id"),
            "append_result": "manual_event_appended_no_trade",
            "manual_event_file": _project_path(event_path),
            "manual_event_file_hash": _file_hash(event_path),
            "result_note": "Manual event was appended to the no-trade shadow observation log.",
        }
    )
    constraints["no_event_submitted_in_status_artifact"] = False
    constraints["manual_event_appended_no_trade"] = True
    status["summary"] = summary
    status["current_capture_result"] = capture_result
    status["constraints"] = constraints
    status["audit"] = validate_risk_diagnostic_shadow_manual_event_capture(status)
    Path(capture_status_path).write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return status


def write_risk_diagnostic_shadow_manual_event_capture_status(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_CAPTURE_STATUS_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
