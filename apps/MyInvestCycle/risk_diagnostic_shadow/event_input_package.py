from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from implementation_readiness.evidence_package_validator import FORBIDDEN_OUTPUT_KEYS
from risk_diagnostic_shadow.first_event_workflow import DEFAULT_OUTPUT_PATH as DEFAULT_FIRST_EVENT_WORKFLOW_PATH
from risk_diagnostic_shadow.manual_event_capture import (
    ALLOWED_MANUAL_REVIEW_STATES,
    DEDUPLICATION_FIELDS,
    SOURCE_LINEAGE_REQUIRED_FIELDS,
    validate_manual_shadow_event,
)
from risk_diagnostic_shadow.observation_framework import (
    COMPONENT_ID,
    CONTEXT_SNAPSHOT_FIELDS,
    EVENT_REQUIRED_FIELDS,
    OUTCOME_REVIEW_FIELDS,
)


DEFAULT_OBSERVATION_LOG_PATH = DATA_DIR / "risk_diagnostic_shadow_observation_log.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_diagnostic_shadow_event_input_package.json"
DEFAULT_TEMPLATE_PATH = DATA_DIR / "risk_diagnostic_shadow_event_input_template.json"


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


def _empty_event_template() -> dict[str, object]:
    return {
        "event_id": "",
        "event_time": "",
        "market_data_as_of": "",
        "component_id": COMPONENT_ID,
        "warning_event_type": "",
        "context_snapshot": {field: "" for field in CONTEXT_SNAPSHOT_FIELDS},
        "source_lineage": {
            "source_artifact_hash": "",
            "event_schema_version": "v14.8",
            "created_by": "",
        },
        "no_trade_observation": {
            "trade_enabled": False,
            "order_generation_enabled": False,
            "broker_connection_enabled": False,
            "position_adjustment_enabled": False,
        },
        "later_outcome_review": {field: None for field in OUTCOME_REVIEW_FIELDS},
        "manual_review_state": "submitted_pending_later_outcome_review",
    }


def _json_schema() -> dict[str, object]:
    return {
        "schema_version": "v14.8",
        "type": "object",
        "required": EVENT_REQUIRED_FIELDS,
        "properties": {
            "event_id": {"type": "string", "minLength": 1},
            "event_time": {"type": "string", "minLength": 1},
            "market_data_as_of": {"type": "string", "minLength": 1},
            "component_id": {"type": "string", "const": COMPONENT_ID},
            "warning_event_type": {"type": "string", "minLength": 1},
            "context_snapshot": {
                "type": "object",
                "required": CONTEXT_SNAPSHOT_FIELDS,
                "additionalProperties": True,
            },
            "source_lineage": {
                "type": "object",
                "required": SOURCE_LINEAGE_REQUIRED_FIELDS,
                "properties": {
                    "source_artifact_hash": {"type": "string", "minLength": 64, "maxLength": 64},
                    "event_schema_version": {"type": "string", "minLength": 1},
                    "created_by": {"type": "string", "minLength": 1},
                },
                "additionalProperties": True,
            },
            "no_trade_observation": {
                "type": "object",
                "required": [
                    "trade_enabled",
                    "order_generation_enabled",
                    "broker_connection_enabled",
                    "position_adjustment_enabled",
                ],
                "properties": {
                    "trade_enabled": {"type": "boolean", "const": False},
                    "order_generation_enabled": {"type": "boolean", "const": False},
                    "broker_connection_enabled": {"type": "boolean", "const": False},
                    "position_adjustment_enabled": {"type": "boolean", "const": False},
                },
                "additionalProperties": True,
            },
            "later_outcome_review": {
                "type": "object",
                "required": OUTCOME_REVIEW_FIELDS,
                "additionalProperties": True,
            },
            "manual_review_state": {
                "type": "string",
                "enum": sorted(ALLOWED_MANUAL_REVIEW_STATES),
            },
        },
        "additionalProperties": False,
    }


def validate_risk_diagnostic_shadow_event_input_file(
    event_file: str | Path,
    *,
    observation_log_path: str | Path = DEFAULT_OBSERVATION_LOG_PATH,
) -> dict[str, object]:
    observation_log = _read_json(observation_log_path)
    if not observation_log:
        raise RuntimeError("observation log missing; rebuild V14.3 first")
    event = _read_json(event_file)
    if not event:
        return {
            "validation_status": "invalid_event_file",
            "event_file": _project_path(event_file),
            "event_submitted": False,
            "implementation_ready": False,
            "trade_enabled": False,
            "errors": ["event_file_missing_or_not_json_object"],
        }
    try:
        validation = validate_manual_shadow_event(observation_log, event)
    except ValueError as exc:
        return {
            "validation_status": "invalid_event_file",
            "event_file": _project_path(event_file),
            "event_file_hash": _file_hash(event_file),
            "event_id": event.get("event_id"),
            "event_submitted": False,
            "implementation_ready": False,
            "trade_enabled": False,
            "errors": [str(exc)],
        }
    return {
        "validation_status": "valid_not_submitted",
        "event_file": _project_path(event_file),
        "event_file_hash": _file_hash(event_file),
        "event_id": validation.get("event_id"),
        "dedupe_key": validation.get("dedupe_key"),
        "event_submitted": False,
        "implementation_ready": False,
        "trade_enabled": False,
        "errors": [],
        "next_allowed_action": "manual_submit_with_explicit_user_approval",
    }


def validate_risk_diagnostic_shadow_event_input_package(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    source_workflow = _mapping(payload.get("source_first_event_workflow"))
    event_template = _mapping(payload.get("event_template"))
    schema = _mapping(payload.get("json_schema"))
    cli = _mapping(payload.get("validation_cli"))
    result = _mapping(payload.get("current_submission_result"))
    guardrails = _mapping(payload.get("no_trade_guardrails"))
    time_safety = _mapping(payload.get("time_safety"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("component_id") != COMPONENT_ID:
        raise AssertionError("component_id must be risk_diagnostic_layer")
    if summary.get("template_status") != "ready":
        raise AssertionError("template status must be ready")
    if summary.get("event_submitted") is not False:
        raise AssertionError("event must not be submitted")
    if summary.get("validated_event_count") != 0:
        raise AssertionError("validated event count must be zero in the default package")
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

    if source_workflow.get("source_workflow_status") != "ready_for_first_manual_event":
        raise AssertionError("source workflow must be ready")
    if source_workflow.get("source_event_count") != 0:
        raise AssertionError("source event count must be zero")
    if source_workflow.get("source_trade_enabled") is not False:
        raise AssertionError("source trade must remain disabled")

    for field in EVENT_REQUIRED_FIELDS:
        if field not in event_template:
            raise AssertionError(f"event template missing {field}")
    if schema.get("schema_version") != "v14.8":
        raise AssertionError("schema version mismatch")
    if set(_sequence(schema.get("required"))) != set(EVENT_REQUIRED_FIELDS):
        raise AssertionError("schema required fields mismatch")
    if cli.get("validates_only") is not True:
        raise AssertionError("CLI must validate only")
    if cli.get("append_to_log_enabled") is not False:
        raise AssertionError("CLI must not append to log")

    if result.get("event_submitted") is not False:
        raise AssertionError("current result must not submit event")
    if result.get("validation_status") != "no_event_file_supplied":
        raise AssertionError("current result must indicate no event file")

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
        "event_input_package_only",
        "template_ready",
        "event_submitted_false",
        "validation_cli_only",
        "does_not_append_event",
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
        "checked_template_status": summary.get("template_status"),
        "checked_event_submitted": summary.get("event_submitted"),
        "checked_validated_event_count": summary.get("validated_event_count"),
        "checked_trade_enabled": summary.get("trade_enabled"),
        "checked_implementation_ready": summary.get("implementation_ready"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_risk_diagnostic_shadow_event_input_package(
    *,
    first_event_workflow_path: str | Path = DEFAULT_FIRST_EVENT_WORKFLOW_PATH,
) -> dict[str, object]:
    workflow = _read_json(first_event_workflow_path)
    if not workflow:
        raise RuntimeError("V14.8 input missing; rebuild V14.7 first event workflow first.")
    workflow_summary = _mapping(workflow.get("summary"))
    if workflow_summary.get("component_id") != COMPONENT_ID:
        raise RuntimeError("V14.7 workflow component mismatch.")
    if workflow_summary.get("workflow_status") != "ready_for_first_manual_event":
        raise RuntimeError("V14.7 workflow must be ready before V14.8 input package.")
    if workflow_summary.get("event_count") != 0:
        raise RuntimeError("V14.8 input package expects no existing event.")
    if workflow_summary.get("trade_enabled") is not False:
        raise RuntimeError("V14.7 trade guardrail must remain disabled.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = _mapping(workflow.get("metadata")).get("as_of")
    input_paths = {"v14_7_first_event_workflow": first_event_workflow_path}
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V14.8 Risk Diagnostic Shadow First Event Submission Input Package",
            "generated_at": generated_at,
            "as_of": as_of,
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Provide the manual event input template and validation CLI without submitting an event or generating decisions.",
        },
        "summary": {
            "component_id": COMPONENT_ID,
            "template_status": "ready",
            "event_submitted": False,
            "validated_event_count": 0,
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
            "conclusion": "risk_diagnostic_shadow_event_input_template_ready_no_submission_no_trade",
            "key_read": "V14.8 provides the first manual event input package; no event file is submitted by default.",
        },
        "source_first_event_workflow": {
            "source_workflow_status": workflow_summary.get("workflow_status"),
            "source_event_count": workflow_summary.get("event_count"),
            "source_quality_queue_count": workflow_summary.get("quality_queue_count"),
            "source_trade_enabled": workflow_summary.get("trade_enabled"),
            "source_hash": _file_hash(first_event_workflow_path),
        },
        "event_template": _empty_event_template(),
        "json_schema": _json_schema(),
        "validation_cli": {
            "script": "scripts/validate_risk_diagnostic_shadow_event_input.py",
            "usage": "python scripts\\validate_risk_diagnostic_shadow_event_input.py --event-file path\\to\\manual_event.json",
            "validates_only": True,
            "append_to_log_enabled": False,
            "requires_explicit_event_file": True,
        },
        "manual_submission_interface": {
            "interface_status": "template_and_cli_ready",
            "web_upload_enabled": False,
            "event_file_required": True,
            "manual_submit_requires_explicit_user_approval": True,
        },
        "current_submission_result": {
            "event_file_supplied": False,
            "validation_status": "no_event_file_supplied",
            "event_submitted": False,
            "validated_event_count": 0,
            "result_note": "No event file is supplied in this package generation run.",
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
                "event_input_package_only",
                "first_manual_event_not_submitted",
                "event_file_not_validated",
                "manual_review_not_approved",
            ],
        },
        "time_safety": {
            "uses_v14_7_first_event_workflow_only": True,
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
            "event_input_package_only": True,
            "template_ready": True,
            "event_submitted_false": True,
            "validation_cli_only": True,
            "does_not_append_event": True,
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
    payload["audit"] = validate_risk_diagnostic_shadow_event_input_package(payload)
    return payload


def write_risk_diagnostic_shadow_event_input_package(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    template_path: str | Path = DEFAULT_TEMPLATE_PATH,
) -> tuple[Path, Path]:
    output = Path(output_path)
    template = Path(template_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    template.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    template.write_text(json.dumps(payload["event_template"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output, template
