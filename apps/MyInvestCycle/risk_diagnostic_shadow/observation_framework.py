from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from implementation_readiness.evidence_package_validator import FORBIDDEN_OUTPUT_KEYS


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RISK_EVIDENCE_PACKAGE_PATH = DATA_DIR / "risk_diagnostic_evidence_package.json"
DEFAULT_GOVERNANCE_FREEZE_PATH = DATA_DIR / "implementation_readiness_governance_freeze.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_diagnostic_shadow_observation_framework.json"

COMPONENT_ID = "risk_diagnostic_layer"
EVENT_REQUIRED_FIELDS = [
    "event_id",
    "event_time",
    "market_data_as_of",
    "component_id",
    "warning_event_type",
    "context_snapshot",
    "source_lineage",
    "no_trade_observation",
    "later_outcome_review",
    "manual_review_state",
]
CONTEXT_SNAPSHOT_FIELDS = [
    "market_phase",
    "risk_state",
    "opportunity_state",
    "risk_gradient_bucket",
    "risk_gradient_score",
    "protection_bucket",
    "protection_score",
    "two_axis_context",
]
OUTCOME_REVIEW_FIELDS = [
    "review_time",
    "review_window_id",
    "later_risk_outcome",
    "false_warning_review",
    "missed_risk_review",
    "stability_review_note",
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


def validate_risk_diagnostic_shadow_framework(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    event_schema = _mapping(payload.get("event_log_schema"))
    empty_log = _mapping(payload.get("shadow_observation_log"))
    guardrails = _mapping(payload.get("no_trade_guardrails"))
    source = _mapping(payload.get("source_evidence_package"))
    promotion = _mapping(payload.get("promotion_gate"))
    time_safety = _mapping(payload.get("time_safety"))
    constraints = _mapping(payload.get("constraints"))

    if summary.get("component_id") != COMPONENT_ID:
        raise AssertionError("component_id must be risk_diagnostic_layer")
    if summary.get("shadow_framework_status") != "defined":
        raise AssertionError("shadow framework must be defined")
    if summary.get("shadow_status") != "planned":
        raise AssertionError("shadow status must be planned")
    if summary.get("observation_only") is not True:
        raise AssertionError("framework must be observation only")
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
    if summary.get("conclusion") != "risk_diagnostic_shadow_framework_defined_observation_only_no_trade":
        raise AssertionError("unexpected conclusion")

    required_fields = set(str(item) for item in _sequence(event_schema.get("required_event_fields")))
    if required_fields != set(EVENT_REQUIRED_FIELDS):
        raise AssertionError("event required fields mismatch")
    context_fields = set(str(item) for item in _sequence(event_schema.get("context_snapshot_fields")))
    if context_fields != set(CONTEXT_SNAPSHOT_FIELDS):
        raise AssertionError("context snapshot fields mismatch")
    outcome_fields = set(str(item) for item in _sequence(event_schema.get("later_outcome_review_fields")))
    if outcome_fields != set(OUTCOME_REVIEW_FIELDS):
        raise AssertionError("outcome review fields mismatch")

    if empty_log.get("log_status") != "initialized_empty":
        raise AssertionError("shadow log must be initialized empty")
    if empty_log.get("live_event_count") != 0:
        raise AssertionError("live event count must be zero")
    if _sequence(empty_log.get("events")):
        raise AssertionError("events must be empty at framework stage")

    for key in (
        "trade_enabled",
        "order_generation_enabled",
        "broker_connection_enabled",
        "position_adjustment_enabled",
        "auto_risk_control_enabled",
    ):
        if guardrails.get(key) is not False:
            raise AssertionError(f"guardrails.{key} must be false")

    if source.get("component_id") != COMPONENT_ID:
        raise AssertionError("source evidence package component mismatch")
    if source.get("source_package_status") != "submitted_blocked_phase_0":
        raise AssertionError("source package must remain blocked phase 0")
    if source.get("source_implementation_ready") is not False:
        raise AssertionError("source package must not be ready")

    if promotion.get("promotion_allowed") is not False:
        raise AssertionError("promotion must be blocked")
    if promotion.get("implementation_ready") is not False:
        raise AssertionError("promotion implementation_ready must be false")
    if "live_shadow_observation_log_missing" not in _sequence(promotion.get("blocking_reasons")):
        raise AssertionError("live shadow missing blocker required")

    if time_safety.get("does_not_read_market_price_data") is not True:
        raise AssertionError("must not read market price data")
    if time_safety.get("does_not_generate_warning_event") is not True:
        raise AssertionError("must not generate warning event")

    required_constraints = [
        "shadow_framework_only",
        "observation_only",
        "does_not_generate_warning_event",
        "does_not_enable_auto_risk_control",
        "does_not_adjust_position",
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
        "checked_shadow_status": summary.get("shadow_status"),
        "checked_live_event_count": empty_log.get("live_event_count"),
        "checked_trade_enabled": summary.get("trade_enabled"),
        "checked_implementation_ready": summary.get("implementation_ready"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_risk_diagnostic_shadow_framework(
    *,
    risk_evidence_package_path: str | Path = DEFAULT_RISK_EVIDENCE_PACKAGE_PATH,
    governance_freeze_path: str | Path = DEFAULT_GOVERNANCE_FREEZE_PATH,
) -> dict[str, object]:
    risk_package = _read_json(risk_evidence_package_path)
    governance_freeze = _read_json(governance_freeze_path)
    if not risk_package or not governance_freeze:
        raise RuntimeError("V14.2 inputs missing; rebuild V13.4 and V14.1 artifacts first.")

    risk_summary = _mapping(risk_package.get("summary"))
    governance_summary = _mapping(governance_freeze.get("summary"))
    if risk_package.get("component_id") != COMPONENT_ID:
        raise RuntimeError("V14.1 risk evidence package component mismatch.")
    if risk_summary.get("package_status") != "submitted_blocked_phase_0":
        raise RuntimeError("V14.1 risk evidence package must remain blocked before V14.2.")
    if governance_summary.get("governance_freeze_status") != "frozen":
        raise RuntimeError("V13.4 governance freeze must remain frozen before V14.2.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = _mapping(risk_package.get("metadata")).get("as_of")
    input_paths = {
        "v14_1_risk_diagnostic_evidence_package": risk_evidence_package_path,
        "v13_4_governance_freeze": governance_freeze_path,
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V14.2 Risk Diagnostic Shadow Observation Framework",
            "generated_at": generated_at,
            "as_of": as_of,
            "input_files": {key: _project_path(path) for key, path in input_paths.items()},
            "input_hashes": {key: _file_hash(path) for key, path in input_paths.items()},
            "purpose": "Define a no-trade shadow observation framework for risk diagnostic warnings without generating events, positions, allocations or trades.",
        },
        "summary": {
            "component_id": COMPONENT_ID,
            "shadow_framework_status": "defined",
            "shadow_status": "planned",
            "observation_only": True,
            "live_event_count": 0,
            "trade_enabled": False,
            "position_adjustment_enabled": False,
            "implementation_gate_result": "blocked",
            "implementation_ready": False,
            "investable_output": False,
            "strategy_output_generated": False,
            "allocation_output_generated": False,
            "trade_ready": False,
            "conclusion": "risk_diagnostic_shadow_framework_defined_observation_only_no_trade",
            "key_read": "V14.2 defines the empty no-trade observation log and review schema needed after V14.1; it does not emit warnings or alter exposure.",
        },
        "source_evidence_package": {
            "component_id": risk_package.get("component_id"),
            "source_package_status": risk_summary.get("package_status"),
            "source_evidence_status": risk_summary.get("evidence_status"),
            "source_implementation_ready": risk_summary.get("implementation_ready"),
            "source_shadow_observation_required": risk_summary.get("shadow_observation_required"),
            "source_hash": _file_hash(risk_evidence_package_path),
        },
        "event_log_schema": {
            "schema_status": "defined",
            "required_event_fields": EVENT_REQUIRED_FIELDS,
            "context_snapshot_fields": CONTEXT_SNAPSHOT_FIELDS,
            "later_outcome_review_fields": OUTCOME_REVIEW_FIELDS,
            "immutable_lineage_fields": [
                "source_artifact_hash",
                "event_schema_version",
                "created_by",
            ],
            "schema_note": "Fields describe what a future warning observation must record; this run creates no warning event.",
        },
        "warning_event_template": {
            "template_status": "defined_not_instantiated",
            "event_id": "future_generated_unique_id",
            "event_time": "future_observation_time",
            "component_id": COMPONENT_ID,
            "warning_event_type": "future_risk_diagnostic_warning",
            "context_snapshot": {field: "future_observed_value" for field in CONTEXT_SNAPSHOT_FIELDS},
            "source_lineage": {
                "source_artifact_hash": "future_source_hash",
                "event_schema_version": "v14.2",
            },
            "no_trade_observation": {
                "trade_enabled": False,
                "order_generation_enabled": False,
                "broker_connection_enabled": False,
                "position_adjustment_enabled": False,
            },
            "later_outcome_review": {field: "future_review_value" for field in OUTCOME_REVIEW_FIELDS},
            "manual_review_state": "future_manual_review_required",
        },
        "shadow_observation_log": {
            "log_status": "initialized_empty",
            "component_id": COMPONENT_ID,
            "live_event_count": 0,
            "events": [],
            "next_allowed_action": "append_future_no_trade_observation_event_after_market_data_freeze",
        },
        "no_trade_guardrails": {
            "trade_enabled": False,
            "order_generation_enabled": False,
            "broker_connection_enabled": False,
            "position_adjustment_enabled": False,
            "auto_risk_control_enabled": False,
            "guardrail_note": "Observation records may be appended later, but they cannot trigger risk control, position change or trading.",
        },
        "promotion_gate": {
            "promotion_allowed": False,
            "implementation_ready": False,
            "required_before_promotion": [
                "future_warning_events_logged",
                "later_outcome_reviews_completed",
                "false_warning_and_missed_risk_cases_reviewed",
                "manual_review_approved",
            ],
            "blocking_reasons": [
                "live_shadow_observation_log_missing",
                "no_later_outcome_review_yet",
                "manual_review_not_approved",
                "v14_1_package_blocked_phase_0",
            ],
        },
        "time_safety": {
            "uses_v14_1_evidence_package_only": True,
            "input_hashes_recorded": True,
            "does_not_read_market_price_data": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_generate_warning_event": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "shadow_framework_only": True,
            "observation_only": True,
            "does_not_generate_warning_event": True,
            "does_not_enable_auto_risk_control": True,
            "does_not_adjust_position": True,
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
    payload["audit"] = validate_risk_diagnostic_shadow_framework(payload)
    return payload


def write_risk_diagnostic_shadow_framework(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
