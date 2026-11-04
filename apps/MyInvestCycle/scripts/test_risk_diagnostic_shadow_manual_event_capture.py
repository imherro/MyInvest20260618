from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    append_manual_shadow_event,
    build_risk_diagnostic_shadow_manual_event_capture_status,
    build_risk_diagnostic_shadow_observation_log,
    build_risk_diagnostic_shadow_observation_review,
    capture_manual_shadow_event_from_file,
    validate_manual_shadow_event,
    validate_risk_diagnostic_shadow_manual_event_capture,
    validate_risk_diagnostic_shadow_observation_review,
    write_risk_diagnostic_shadow_observation_log,
)


def _valid_event() -> dict[str, object]:
    return {
        "event_id": "manual_shadow_event_20260707_risk_diagnostic_001",
        "event_time": "2026-07-07T15:30:00+08:00",
        "market_data_as_of": "20260707",
        "component_id": "risk_diagnostic_layer",
        "warning_event_type": "manual_risk_diagnostic_observation",
        "context_snapshot": {
            "market_phase": "observed_macro_phase",
            "risk_state": "observed_short_term_risk_state",
            "opportunity_state": "observed_opportunity_state",
            "risk_gradient_bucket": "observed_gradient_bucket",
            "risk_gradient_score": "observed_gradient_score",
            "protection_bucket": "observed_protection_bucket",
            "protection_score": "observed_protection_score",
            "two_axis_context": "observed_two_axis_context",
        },
        "source_lineage": {
            "source_artifact_hash": "a" * 64,
            "event_schema_version": "v14.5",
            "created_by": "manual_operator",
        },
        "no_trade_observation": {
            "trade_enabled": False,
            "order_generation_enabled": False,
            "broker_connection_enabled": False,
            "position_adjustment_enabled": False,
        },
        "later_outcome_review": {
            "review_time": "pending",
            "review_window_id": "pending",
            "later_risk_outcome": "pending",
            "false_warning_review": "pending",
            "missed_risk_review": "pending",
            "stability_review_note": "pending",
        },
        "manual_review_state": "submitted_pending_later_outcome_review",
    }


def main() -> None:
    log_payload = build_risk_diagnostic_shadow_observation_log()
    status = build_risk_diagnostic_shadow_manual_event_capture_status()
    summary = status["summary"]
    controls = status["manual_capture_controls"]
    source = status["source_observation_log"]
    current_result = status["current_capture_result"]
    guardrails = status["no_trade_guardrails"]
    promotion = status["promotion_gate"]
    time_safety = status["time_safety"]
    constraints = status["constraints"]
    audit = status["audit"]

    assert summary["component_id"] == "risk_diagnostic_layer"
    assert summary["manual_capture_status"] == "ready_for_manual_input"
    assert summary["source_event_count"] == 0
    assert summary["submitted_event_count"] == 0
    assert summary["auto_trigger_enabled"] is False
    assert summary["auto_warning_enabled"] is False
    assert summary["trade_enabled"] is False
    assert summary["position_adjustment_enabled"] is False
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False

    assert source["source_observation_status"] == "active"
    assert source["source_event_count"] == 0
    assert source["source_auto_trigger_enabled"] is False
    assert source["source_trade_enabled"] is False
    assert len(source["source_hash"]) == 64

    assert controls["append_mode"] == "manual_event_file_only"
    assert controls["duplicate_detection_enabled"] is True
    assert controls["append_only_log"] is True
    assert controls["manual_review_required"] is True
    assert controls["auto_event_generation_enabled"] is False
    assert controls["auto_warning_detection_enabled"] is False
    assert controls["market_data_reader_enabled"] is False
    assert "source_artifact_hash" in controls["source_lineage_required_fields"]

    assert current_result["event_file_supplied"] is False
    assert current_result["submitted_event_count"] == 0
    assert current_result["append_result"] == "no_event_submitted"

    assert guardrails["trade_enabled"] is False
    assert guardrails["order_generation_enabled"] is False
    assert guardrails["broker_connection_enabled"] is False
    assert guardrails["position_adjustment_enabled"] is False
    assert guardrails["auto_risk_control_enabled"] is False

    assert promotion["promotion_allowed"] is False
    assert promotion["implementation_ready"] is False
    assert "manual_event_capture_capability_only" in promotion["blocking_reasons"]

    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_auto_generate_warning"] is True
    assert time_safety["does_not_auto_judge_risk"] is True
    assert time_safety["does_not_auto_adjust_risk"] is True

    assert constraints["manual_capture_capability_only"] is True
    assert constraints["no_event_submitted_in_status_artifact"] is True
    assert constraints["manual_append_only"] is True
    assert constraints["append_only_log"] is True
    assert constraints["duplicate_detection_enabled"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_risk_diagnostic_shadow_manual_event_capture(status)["audit_status"] == "passed"

    event = _valid_event()
    assert validate_manual_shadow_event(log_payload, event)["validation_status"] == "passed"
    updated_log = append_manual_shadow_event(log_payload, event)
    updated_summary = updated_log["summary"]
    updated_body = updated_log["shadow_observation_log"]
    assert updated_summary["log_status"] == "active_with_manual_events"
    assert updated_summary["event_count"] == 1
    assert updated_summary["trade_enabled"] is False
    assert updated_summary["implementation_ready"] is False
    assert updated_body["event_count"] == 1
    assert len(updated_body["events"]) == 1

    try:
        append_manual_shadow_event(updated_log, event)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate manual event must be rejected")

    rejected_event = dict(event)
    rejected_event["event_id"] = "manual_shadow_event_rejected_trade_enabled"
    rejected_event["source_lineage"] = {
        "source_artifact_hash": "b" * 64,
        "event_schema_version": "v14.5",
        "created_by": "manual_operator",
    }
    rejected_event["no_trade_observation"] = {
        "trade_enabled": True,
        "order_generation_enabled": False,
        "broker_connection_enabled": False,
        "position_adjustment_enabled": False,
    }
    try:
        append_manual_shadow_event(log_payload, rejected_event)
    except ValueError as exc:
        assert "no-trade guardrails" in str(exc)
    else:
        raise AssertionError("manual event with trade enabled must be rejected")

    rejected_hash_event = dict(event)
    rejected_hash_event["event_id"] = "manual_shadow_event_rejected_hash"
    rejected_hash_event["source_lineage"] = {
        "source_artifact_hash": "not_a_hash",
        "event_schema_version": "v14.5",
        "created_by": "manual_operator",
    }
    try:
        append_manual_shadow_event(log_payload, rejected_hash_event)
    except ValueError as exc:
        assert "sha256" in str(exc)
    else:
        raise AssertionError("manual event with invalid source hash must be rejected")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        log_path = tmp / "risk_diagnostic_shadow_observation_log.json"
        event_path = tmp / "manual_event.json"
        status_path = tmp / "risk_diagnostic_shadow_manual_event_capture.json"
        write_risk_diagnostic_shadow_observation_log(log_payload, log_path)
        event_path.write_text(json.dumps(event, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        captured_status = capture_manual_shadow_event_from_file(
            event_path,
            observation_log_path=log_path,
            capture_status_path=status_path,
        )
        assert status_path.exists()
        assert captured_status["summary"]["submitted_event_count"] == 1
        assert captured_status["summary"]["source_event_count"] == 1
        assert captured_status["current_capture_result"]["event_file_supplied"] is True
        assert captured_status["current_capture_result"]["append_result"] == "manual_event_appended_no_trade"
        assert captured_status["audit"]["audit_status"] == "passed"

        review_payload = build_risk_diagnostic_shadow_observation_review(observation_log_path=log_path)
        assert review_payload["summary"]["review_status"] == "events_pending_manual_review"
        assert review_payload["summary"]["event_count"] == 1
        assert review_payload["summary"]["reviewed_event_count"] == 0
        assert review_payload["review_result"]["event_reviews"] == []
        assert review_payload["summary"]["trade_enabled"] is False
        assert validate_risk_diagnostic_shadow_observation_review(review_payload)["audit_status"] == "passed"

    joined = " ".join(str(value) for value in status.values())
    for code in ("510" + "300", "510" + "500", "510" + "880", "511" + "880", "159" + "915"):
        assert code not in joined
    assert "%" not in joined

    print("test_risk_diagnostic_shadow_manual_event_capture ok")


if __name__ == "__main__":
    main()
