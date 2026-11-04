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
    EVENT_REQUIRED_FIELDS,
)


DEFAULT_SHADOW_FRAMEWORK_PATH = DATA_DIR / "risk_diagnostic_shadow_observation_framework.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_diagnostic_shadow_observation_log.json"


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


def _event_has_no_trade_guardrails(event: Mapping[str, Any]) -> bool:
    guardrails = _mapping(event.get("no_trade_observation"))
    return all(
        guardrails.get(key) is False
        for key in (
            "trade_enabled",
            "order_generation_enabled",
            "broker_connection_enabled",
            "position_adjustment_enabled",
        )
    )


def append_no_trade_observation_event(
    log_payload: Mapping[str, Any],
    event: Mapping[str, Any],
) -> dict[str, object]:
    """Return a new log payload with a manually supplied no-trade event appended.

    This helper does not detect warnings, read market data or write files. A future
    run must provide the event explicitly after data is frozen and still pass the
    no-trade guardrails.
    """
    missing = [field for field in EVENT_REQUIRED_FIELDS if field not in event]
    if missing:
        raise ValueError(f"missing event fields: {missing}")
    if event.get("component_id") != COMPONENT_ID:
        raise ValueError("event component_id mismatch")
    if not _event_has_no_trade_guardrails(event):
        raise ValueError("event does not satisfy no-trade guardrails")

    payload = deepcopy(dict(log_payload))
    log = dict(_mapping(payload.get("shadow_observation_log")))
    events = list(_sequence(log.get("events")))
    events.append(dict(event))
    log["events"] = events
    log["event_count"] = len(events)
    log["live_event_count"] = len(events)
    log["last_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload["shadow_observation_log"] = log
    summary = dict(_mapping(payload.get("summary")))
    summary["event_count"] = len(events)
    summary["live_event_count"] = len(events)
    payload["summary"] = summary
    return payload


def validate_risk_diagnostic_shadow_observation_log(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    source = _mapping(payload.get("source_shadow_framework"))
    controls = _mapping(payload.get("observation_controls"))
    log = _mapping(payload.get("shadow_observation_log"))
    guardrails = _mapping(payload.get("no_trade_guardrails"))
    time_safety = _mapping(payload.get("time_safety"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("component_id") != COMPONENT_ID:
        raise AssertionError("component_id must be risk_diagnostic_layer")
    if summary.get("observation_status") != "active":
        raise AssertionError("observation status must be active")
    if summary.get("log_status") != "active_empty":
        raise AssertionError("log status must be active_empty")
    if summary.get("event_count") != 0:
        raise AssertionError("event count must be zero on initialization")
    if summary.get("live_event_count") != 0:
        raise AssertionError("live event count must be zero on initialization")
    if summary.get("auto_trigger_enabled") is not False:
        raise AssertionError("auto trigger must be disabled")
    if summary.get("manual_append_only") is not True:
        raise AssertionError("log must be manual append only")
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
    if summary.get("conclusion") != "risk_diagnostic_shadow_log_active_empty_no_trade":
        raise AssertionError("unexpected conclusion")

    if source.get("source_shadow_framework_status") != "defined":
        raise AssertionError("source framework must be defined")
    if source.get("source_shadow_status") != "planned":
        raise AssertionError("source shadow status must be planned")
    if source.get("source_trade_enabled") is not False:
        raise AssertionError("source trade must be disabled")

    if controls.get("append_mode") != "manual_only":
        raise AssertionError("append mode must be manual_only")
    if controls.get("auto_warning_detection_enabled") is not False:
        raise AssertionError("auto warning detection must be disabled")
    if controls.get("market_data_reader_enabled") is not False:
        raise AssertionError("market data reader must be disabled")

    if log.get("log_status") != "active_empty":
        raise AssertionError("shadow log must be active empty")
    if log.get("event_count") != 0:
        raise AssertionError("shadow log event count must be zero")
    if _sequence(log.get("events")):
        raise AssertionError("shadow log events must be empty")

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
    if time_safety.get("does_not_auto_trigger_warning") is not True:
        raise AssertionError("must not auto trigger warning")

    required_constraints = [
        "observation_log_initialization_only",
        "active_empty_log_only",
        "manual_append_only",
        "does_not_auto_trigger_warning",
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
        "checked_observation_status": summary.get("observation_status"),
        "checked_event_count": summary.get("event_count"),
        "checked_auto_trigger_enabled": summary.get("auto_trigger_enabled"),
        "checked_trade_enabled": summary.get("trade_enabled"),
        "checked_implementation_ready": summary.get("implementation_ready"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_risk_diagnostic_shadow_observation_log(
    *,
    shadow_framework_path: str | Path = DEFAULT_SHADOW_FRAMEWORK_PATH,
) -> dict[str, object]:
    framework = _read_json(shadow_framework_path)
    if not framework:
        raise RuntimeError("V14.3 input missing; rebuild V14.2 shadow framework first.")
    framework_summary = _mapping(framework.get("summary"))
    if framework_summary.get("component_id") != COMPONENT_ID:
        raise RuntimeError("V14.2 shadow framework component mismatch.")
    if framework_summary.get("shadow_framework_status") != "defined":
        raise RuntimeError("V14.2 shadow framework must be defined before V14.3.")
    if framework_summary.get("trade_enabled") is not False:
        raise RuntimeError("V14.2 trade guardrail must remain disabled.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = _mapping(framework.get("metadata")).get("as_of")
    input_paths = {"v14_2_shadow_framework": shadow_framework_path}
    event_fields = list(_sequence(_mapping(framework.get("event_log_schema")).get("required_event_fields")))
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V14.3 Risk Diagnostic Shadow Observation Log Initialization",
            "generated_at": generated_at,
            "as_of": as_of,
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Initialize an active empty no-trade shadow observation log without automatically generating warning events.",
        },
        "summary": {
            "component_id": COMPONENT_ID,
            "observation_status": "active",
            "log_status": "active_empty",
            "event_count": 0,
            "live_event_count": 0,
            "manual_append_only": True,
            "auto_trigger_enabled": False,
            "trade_enabled": False,
            "position_adjustment_enabled": False,
            "implementation_gate_result": "blocked",
            "implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "risk_diagnostic_shadow_log_active_empty_no_trade",
            "key_read": "V14.3 activates an empty no-trade observation log for future manual warning records; no warning is generated now.",
        },
        "source_shadow_framework": {
            "source_shadow_framework_status": framework_summary.get("shadow_framework_status"),
            "source_shadow_status": framework_summary.get("shadow_status"),
            "source_trade_enabled": framework_summary.get("trade_enabled"),
            "source_implementation_ready": framework_summary.get("implementation_ready"),
            "source_hash": _file_hash(shadow_framework_path),
        },
        "observation_controls": {
            "append_mode": "manual_only",
            "auto_warning_detection_enabled": False,
            "market_data_reader_enabled": False,
            "requires_market_data_freeze_before_append": True,
            "requires_source_hash_before_append": True,
            "requires_no_trade_guardrails_before_append": True,
            "dedupe_key_fields": [
                "event_time",
                "market_data_as_of",
                "warning_event_type",
                "source_artifact_hash",
            ],
        },
        "event_schema_snapshot": {
            "schema_source": "v14_2_shadow_framework",
            "required_event_field_count": len(event_fields),
            "required_event_fields": event_fields,
        },
        "shadow_observation_log": {
            "log_id": "risk_diagnostic_shadow_observation_log",
            "component_id": COMPONENT_ID,
            "log_status": "active_empty",
            "created_at": generated_at,
            "last_updated": generated_at,
            "event_count": 0,
            "live_event_count": 0,
            "events": [],
        },
        "no_trade_guardrails": {
            "trade_enabled": False,
            "order_generation_enabled": False,
            "broker_connection_enabled": False,
            "position_adjustment_enabled": False,
            "auto_risk_control_enabled": False,
            "guardrail_note": "Log activation only permits future manual no-trade observation records.",
        },
        "promotion_gate": {
            "promotion_allowed": False,
            "implementation_ready": False,
            "blocking_reasons": [
                "event_count_zero",
                "no_later_outcome_review_yet",
                "manual_review_not_approved",
                "log_records_observation_only",
            ],
        },
        "time_safety": {
            "uses_v14_2_shadow_framework_only": True,
            "input_hashes_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_auto_trigger_warning": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "observation_log_initialization_only": True,
            "active_empty_log_only": True,
            "manual_append_only": True,
            "does_not_auto_trigger_warning": True,
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
    payload["audit"] = validate_risk_diagnostic_shadow_observation_log(payload)
    return payload


def write_risk_diagnostic_shadow_observation_log(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
