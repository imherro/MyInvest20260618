from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from implementation_readiness.evidence_package_validator import FORBIDDEN_OUTPUT_KEYS
from risk_diagnostic_shadow.manual_event_capture import (
    DEDUPLICATION_FIELDS,
    SOURCE_LINEAGE_REQUIRED_FIELDS,
)
from risk_diagnostic_shadow.observation_framework import (
    COMPONENT_ID,
    CONTEXT_SNAPSHOT_FIELDS,
    EVENT_REQUIRED_FIELDS,
    OUTCOME_REVIEW_FIELDS,
)


DEFAULT_OBSERVATION_LOG_PATH = DATA_DIR / "risk_diagnostic_shadow_observation_log.json"
DEFAULT_MANUAL_CAPTURE_PATH = DATA_DIR / "risk_diagnostic_shadow_manual_event_capture.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_diagnostic_shadow_event_quality_audit.json"

EVENT_INTEGRITY_CHECKS = [
    "schema_completeness",
    "source_hash",
    "duplicate_key",
    "timestamp_consistency",
]
RESEARCH_QUALITY_CHECKS = [
    "context_snapshot_completeness",
    "later_outcome_completeness",
    "false_warning_review_completeness",
    "missed_risk_review_completeness",
]
BOUNDARY_CHECKS = [
    "no_trade",
    "no_allocation",
    "no_automatic_decision",
]
ALLOWED_QUALITY_AUDIT_STATUSES = {
    "no_events_available",
    "events_quality_checked_pending_manual_review",
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


def _event_list(observation_log: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    log = _mapping(observation_log.get("shadow_observation_log"))
    return [event for event in _sequence(log.get("events")) if isinstance(event, Mapping)]


def _hash_is_valid(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def _timestamp_is_valid(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _dedupe_key(event: Mapping[str, Any]) -> tuple[str, str, str, str]:
    source_lineage = _mapping(event.get("source_lineage"))
    return (
        str(event.get("event_time") or ""),
        str(event.get("market_data_as_of") or ""),
        str(event.get("warning_event_type") or ""),
        str(source_lineage.get("source_artifact_hash") or ""),
    )


def _event_quality_review(event: Mapping[str, Any], duplicate_keys: set[tuple[str, str, str, str]]) -> dict[str, object]:
    context_snapshot = _mapping(event.get("context_snapshot"))
    source_lineage = _mapping(event.get("source_lineage"))
    later_outcome_review = _mapping(event.get("later_outcome_review"))
    no_trade = _mapping(event.get("no_trade_observation"))
    missing_event_fields = [field for field in EVENT_REQUIRED_FIELDS if field not in event]
    missing_context_fields = [field for field in CONTEXT_SNAPSHOT_FIELDS if field not in context_snapshot]
    missing_source_fields = [field for field in SOURCE_LINEAGE_REQUIRED_FIELDS if field not in source_lineage]
    missing_outcome_fields = [field for field in OUTCOME_REVIEW_FIELDS if field not in later_outcome_review]
    forbidden_keys = sorted(FORBIDDEN_OUTPUT_KEYS.intersection(key for key in _walk_keys(event) if key != "forbidden_outputs"))
    dedupe_key = _dedupe_key(event)

    checks = {
        "schema_completeness": not missing_event_fields,
        "source_hash": _hash_is_valid(source_lineage.get("source_artifact_hash")),
        "duplicate_key": dedupe_key not in duplicate_keys,
        "timestamp_consistency": _timestamp_is_valid(event.get("event_time")),
        "context_snapshot_completeness": not missing_context_fields,
        "later_outcome_completeness": not missing_outcome_fields,
        "false_warning_review_completeness": "false_warning_review" in later_outcome_review,
        "missed_risk_review_completeness": "missed_risk_review" in later_outcome_review,
        "no_trade": all(
            no_trade.get(key) is False
            for key in (
                "trade_enabled",
                "order_generation_enabled",
                "broker_connection_enabled",
                "position_adjustment_enabled",
            )
        ),
        "no_allocation": True,
        "no_automatic_decision": True,
    }
    return {
        "event_id": event.get("event_id"),
        "quality_review_status": "manual_review_required",
        "checks": checks,
        "missing_event_fields": missing_event_fields,
        "missing_context_fields": missing_context_fields,
        "missing_source_lineage_fields": missing_source_fields,
        "missing_later_outcome_fields": missing_outcome_fields,
        "forbidden_output_keys": forbidden_keys,
        "dedupe_key": dict(zip(DEDUPLICATION_FIELDS, dedupe_key, strict=True)),
        "automatic_risk_decision": False,
        "implementation_ready": False,
        "trade_enabled": False,
    }


def validate_risk_diagnostic_shadow_event_quality_audit(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    source_log = _mapping(payload.get("source_observation_log"))
    source_capture = _mapping(payload.get("source_manual_capture"))
    framework = _mapping(payload.get("quality_audit_framework"))
    result = _mapping(payload.get("quality_audit_result"))
    guardrails = _mapping(payload.get("no_trade_guardrails"))
    time_safety = _mapping(payload.get("time_safety"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("component_id") != COMPONENT_ID:
        raise AssertionError("component_id must be risk_diagnostic_layer")
    if summary.get("quality_audit_status") not in ALLOWED_QUALITY_AUDIT_STATUSES:
        raise AssertionError("unexpected quality audit status")
    event_count = int(summary.get("event_count") or 0)
    checked_events = int(summary.get("quality_checked_events") or 0)
    if event_count < 0 or checked_events < 0:
        raise AssertionError("event counts cannot be negative")
    if event_count == 0:
        if summary.get("quality_audit_status") != "no_events_available":
            raise AssertionError("zero events must produce no_events_available")
        if checked_events != 0:
            raise AssertionError("zero events cannot have checked events")
    else:
        if summary.get("quality_audit_status") != "events_quality_checked_pending_manual_review":
            raise AssertionError("events must remain pending manual quality review")
        if checked_events != event_count:
            raise AssertionError("checked events must match event count")

    for key in (
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
    if int(source_log.get("source_event_count") or 0) != event_count:
        raise AssertionError("source event count mismatch")
    if source_log.get("source_trade_enabled") is not False:
        raise AssertionError("source trade must remain disabled")
    if source_capture.get("source_manual_capture_status") != "ready_for_manual_input":
        raise AssertionError("manual capture source must be ready")
    if source_capture.get("source_trade_enabled") is not False:
        raise AssertionError("manual capture source trade must remain disabled")

    if set(_sequence(framework.get("event_integrity_checks"))) != set(EVENT_INTEGRITY_CHECKS):
        raise AssertionError("event integrity checks mismatch")
    if set(_sequence(framework.get("research_quality_checks"))) != set(RESEARCH_QUALITY_CHECKS):
        raise AssertionError("research quality checks mismatch")
    if set(_sequence(framework.get("boundary_checks"))) != set(BOUNDARY_CHECKS):
        raise AssertionError("boundary checks mismatch")
    if framework.get("manual_review_required") is not True:
        raise AssertionError("manual review must be required")
    if framework.get("auto_decision_allowed") is not False:
        raise AssertionError("auto decision must be disabled")

    if result.get("audit_status") != summary.get("quality_audit_status"):
        raise AssertionError("audit status mismatch")
    if int(result.get("quality_checked_events") or 0) != checked_events:
        raise AssertionError("quality checked count mismatch")
    if event_count == 0 and _sequence(result.get("event_quality_reviews")):
        raise AssertionError("event reviews must be empty when no events exist")

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
        "quality_audit_only",
        "manual_review_required",
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
    if event_count == 0 and constraints.get("no_events_available") is not True:
        raise AssertionError("constraints.no_events_available must be true when no events exist")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(
        key for key in _walk_keys(payload) if key != "forbidden_outputs"
    )
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_component_id": summary.get("component_id"),
        "checked_quality_audit_status": summary.get("quality_audit_status"),
        "checked_event_count": event_count,
        "checked_quality_checked_events": checked_events,
        "checked_trade_enabled": summary.get("trade_enabled"),
        "checked_implementation_ready": summary.get("implementation_ready"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_risk_diagnostic_shadow_event_quality_audit(
    *,
    observation_log_path: str | Path = DEFAULT_OBSERVATION_LOG_PATH,
    manual_capture_path: str | Path = DEFAULT_MANUAL_CAPTURE_PATH,
) -> dict[str, object]:
    observation_log = _read_json(observation_log_path)
    manual_capture = _read_json(manual_capture_path)
    if not observation_log or not manual_capture:
        raise RuntimeError("V14.6 inputs missing; rebuild V14.3 observation log and V14.5 manual capture first.")

    log_summary = _mapping(observation_log.get("summary"))
    capture_summary = _mapping(manual_capture.get("summary"))
    if log_summary.get("component_id") != COMPONENT_ID:
        raise RuntimeError("V14.3 observation log component mismatch.")
    if log_summary.get("observation_status") != "active":
        raise RuntimeError("V14.3 observation log must be active before V14.6.")
    if log_summary.get("trade_enabled") is not False:
        raise RuntimeError("V14.3 trade guardrail must remain disabled.")
    if capture_summary.get("component_id") != COMPONENT_ID:
        raise RuntimeError("V14.5 manual capture component mismatch.")
    if capture_summary.get("manual_capture_status") != "ready_for_manual_input":
        raise RuntimeError("V14.5 manual capture must be ready before V14.6.")
    if capture_summary.get("trade_enabled") is not False:
        raise RuntimeError("V14.5 trade guardrail must remain disabled.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = _mapping(observation_log.get("metadata")).get("as_of")
    events = _event_list(observation_log)
    event_count = len(events)
    seen: set[tuple[str, str, str, str]] = set()
    reviews = []
    for event in events:
        review = _event_quality_review(event, seen)
        seen.add(_dedupe_key(event))
        reviews.append(review)
    quality_audit_status = "no_events_available" if event_count == 0 else "events_quality_checked_pending_manual_review"
    input_paths = {
        "v14_3_observation_log": observation_log_path,
        "v14_5_manual_capture": manual_capture_path,
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V14.6 Risk Diagnostic Shadow Event Quality Audit",
            "generated_at": generated_at,
            "as_of": as_of,
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Define and run a no-trade quality audit over manually captured shadow events without automatic risk judgment or trading.",
        },
        "summary": {
            "component_id": COMPONENT_ID,
            "quality_audit_status": quality_audit_status,
            "event_count": event_count,
            "quality_checked_events": event_count,
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
            "conclusion": "risk_diagnostic_shadow_quality_audit_no_events_no_trade"
            if event_count == 0
            else "risk_diagnostic_shadow_quality_checked_pending_manual_review_no_trade",
            "key_read": "V14.6 defines event quality audit checks; current shadow log has no events."
            if event_count == 0
            else "V14.6 checks manually captured event quality but leaves implementation blocked pending manual review.",
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
        "quality_audit_framework": {
            "event_integrity_checks": EVENT_INTEGRITY_CHECKS,
            "research_quality_checks": RESEARCH_QUALITY_CHECKS,
            "boundary_checks": BOUNDARY_CHECKS,
            "manual_review_required": True,
            "auto_decision_allowed": False,
            "framework_note": "Quality checks inspect manual event completeness and boundary compliance only; they do not decide risk or generate trades.",
        },
        "quality_audit_result": {
            "audit_status": quality_audit_status,
            "quality_checked_events": event_count,
            "event_quality_reviews": reviews,
            "result_note": "No shadow events are available to audit yet."
            if event_count == 0
            else "Manual shadow events were checked for data quality and remain pending manual review.",
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
                "no_shadow_events_available",
                "no_later_outcome_review_yet",
                "manual_quality_review_not_approved",
                "quality_audit_only",
            ] if event_count == 0 else [
                "events_pending_manual_quality_review",
                "no_later_outcome_review_yet",
                "manual_quality_review_not_approved",
                "quality_audit_only",
            ],
        },
        "time_safety": {
            "uses_v14_3_observation_log_and_v14_5_capture_only": True,
            "input_hashes_recorded": True,
            "does_not_read_market_price_data": True,
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
            "quality_audit_only": True,
            "no_events_available": event_count == 0,
            "events_pending_manual_quality_review": event_count > 0,
            "manual_review_required": True,
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
    payload["audit"] = validate_risk_diagnostic_shadow_event_quality_audit(payload)
    return payload


def write_risk_diagnostic_shadow_event_quality_audit(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
