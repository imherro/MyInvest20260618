from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_event_quality_audit,
    build_risk_diagnostic_shadow_manual_event_capture_status,
    build_risk_diagnostic_shadow_observation_log,
    capture_manual_shadow_event_from_file,
    validate_risk_diagnostic_shadow_event_quality_audit,
    write_risk_diagnostic_shadow_manual_event_capture_status,
    write_risk_diagnostic_shadow_observation_log,
)


def _valid_event() -> dict[str, object]:
    return {
        "event_id": "manual_shadow_event_quality_20260707_001",
        "event_time": "2026-07-07T15:30:00+08:00",
        "market_data_as_of": "20260707",
        "component_id": "risk_diagnostic_layer",
        "warning_event_type": "manual_quality_audit_observation",
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
            "source_artifact_hash": "c" * 64,
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
    payload = build_risk_diagnostic_shadow_event_quality_audit()
    metadata = payload["metadata"]
    summary = payload["summary"]
    source_log = payload["source_observation_log"]
    source_capture = payload["source_manual_capture"]
    framework = payload["quality_audit_framework"]
    result = payload["quality_audit_result"]
    guardrails = payload["no_trade_guardrails"]
    promotion = payload["promotion_gate"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V14.6 Risk Diagnostic Shadow Event Quality Audit"
    assert len(metadata["input_hashes"]) == 2
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["component_id"] == "risk_diagnostic_layer"
    assert summary["quality_audit_status"] == "no_events_available"
    assert summary["event_count"] == 0
    assert summary["quality_checked_events"] == 0
    assert summary["auto_decision_enabled"] is False
    assert summary["auto_warning_enabled"] is False
    assert summary["trade_enabled"] is False
    assert summary["position_adjustment_enabled"] is False
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False

    assert source_log["source_observation_status"] == "active"
    assert source_log["source_event_count"] == 0
    assert source_log["source_auto_trigger_enabled"] is False
    assert source_log["source_trade_enabled"] is False
    assert len(source_log["source_hash"]) == 64

    assert source_capture["source_manual_capture_status"] == "ready_for_manual_input"
    assert source_capture["source_trade_enabled"] is False
    assert len(source_capture["source_hash"]) == 64

    assert "schema_completeness" in framework["event_integrity_checks"]
    assert "later_outcome_completeness" in framework["research_quality_checks"]
    assert "no_trade" in framework["boundary_checks"]
    assert framework["manual_review_required"] is True
    assert framework["auto_decision_allowed"] is False

    assert result["audit_status"] == "no_events_available"
    assert result["quality_checked_events"] == 0
    assert result["event_quality_reviews"] == []

    assert guardrails["trade_enabled"] is False
    assert guardrails["order_generation_enabled"] is False
    assert guardrails["broker_connection_enabled"] is False
    assert guardrails["position_adjustment_enabled"] is False
    assert guardrails["auto_risk_control_enabled"] is False

    assert promotion["promotion_allowed"] is False
    assert promotion["implementation_ready"] is False
    assert "no_shadow_events_available" in promotion["blocking_reasons"]

    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_auto_generate_event"] is True
    assert time_safety["does_not_auto_generate_warning"] is True
    assert time_safety["does_not_auto_judge_risk"] is True

    assert constraints["quality_audit_only"] is True
    assert constraints["no_events_available"] is True
    assert constraints["manual_review_required"] is True
    assert constraints["does_not_auto_generate_event"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_risk_diagnostic_shadow_event_quality_audit(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        log_path = tmp / "risk_diagnostic_shadow_observation_log.json"
        capture_path = tmp / "risk_diagnostic_shadow_manual_event_capture.json"
        event_path = tmp / "manual_event.json"
        base_log = build_risk_diagnostic_shadow_observation_log()
        base_capture = build_risk_diagnostic_shadow_manual_event_capture_status()
        write_risk_diagnostic_shadow_observation_log(base_log, log_path)
        write_risk_diagnostic_shadow_manual_event_capture_status(base_capture, capture_path)
        event_path.write_text(json.dumps(_valid_event(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        capture_manual_shadow_event_from_file(
            event_path,
            observation_log_path=log_path,
            capture_status_path=capture_path,
        )

        event_payload = build_risk_diagnostic_shadow_event_quality_audit(
            observation_log_path=log_path,
            manual_capture_path=capture_path,
        )
        event_summary = event_payload["summary"]
        event_result = event_payload["quality_audit_result"]
        event_review = event_result["event_quality_reviews"][0]
        assert event_summary["quality_audit_status"] == "events_quality_checked_pending_manual_review"
        assert event_summary["event_count"] == 1
        assert event_summary["quality_checked_events"] == 1
        assert event_summary["auto_decision_enabled"] is False
        assert event_summary["trade_enabled"] is False
        assert event_summary["implementation_ready"] is False
        assert event_review["quality_review_status"] == "manual_review_required"
        assert event_review["checks"]["schema_completeness"] is True
        assert event_review["checks"]["source_hash"] is True
        assert event_review["checks"]["duplicate_key"] is True
        assert event_review["checks"]["timestamp_consistency"] is True
        assert event_review["checks"]["no_trade"] is True
        assert event_review["checks"]["no_automatic_decision"] is True
        assert event_review["automatic_risk_decision"] is False
        assert event_review["trade_enabled"] is False
        assert validate_risk_diagnostic_shadow_event_quality_audit(event_payload)["audit_status"] == "passed"

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "510" + "880", "511" + "880", "159" + "915"):
        assert code not in joined
    assert "%" not in joined

    print("test_risk_diagnostic_shadow_event_quality_audit ok")


if __name__ == "__main__":
    main()
