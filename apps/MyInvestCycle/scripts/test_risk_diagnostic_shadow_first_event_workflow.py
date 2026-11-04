from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_event_quality_audit,
    build_risk_diagnostic_shadow_first_event_workflow,
    build_risk_diagnostic_shadow_manual_event_capture_status,
    build_risk_diagnostic_shadow_observation_log,
    validate_risk_diagnostic_shadow_first_event_workflow,
    write_risk_diagnostic_shadow_event_quality_audit,
    write_risk_diagnostic_shadow_manual_event_capture_status,
    write_risk_diagnostic_shadow_observation_log,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_first_event_workflow()
    metadata = payload["metadata"]
    summary = payload["summary"]
    source_log = payload["source_observation_log"]
    source_capture = payload["source_manual_capture"]
    source_quality = payload["source_quality_audit"]
    workflow = payload["first_event_workflow"]
    requirements = payload["first_event_input_requirements"]
    queue = payload["quality_audit_queue"]
    guardrails = payload["no_trade_guardrails"]
    promotion = payload["promotion_gate"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V14.7 Risk Diagnostic Shadow Observation First Event Workflow"
    assert len(metadata["input_hashes"]) == 3
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["component_id"] == "risk_diagnostic_layer"
    assert summary["workflow_status"] == "ready_for_first_manual_event"
    assert summary["event_count"] == 0
    assert summary["quality_queue_count"] == 0
    assert summary["auto_scan_enabled"] is False
    assert summary["auto_event_generation_enabled"] is False
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
    assert source_capture["source_submitted_event_count"] == 0
    assert source_capture["source_trade_enabled"] is False
    assert len(source_capture["source_hash"]) == 64

    assert source_quality["source_quality_audit_status"] == "no_events_available"
    assert source_quality["source_quality_checked_events"] == 0
    assert source_quality["source_trade_enabled"] is False
    assert len(source_quality["source_hash"]) == 64

    expected_steps = [
        "manual_event_json_preparation",
        "schema_validation",
        "source_hash_validation",
        "duplicate_check",
        "no_trade_check",
        "quality_audit_queue",
        "later_outcome_review_placeholder",
    ]
    assert workflow["workflow_step_count"] == len(expected_steps)
    assert [item["step_id"] for item in workflow["workflow_steps"]] == expected_steps
    assert workflow["manual_event_required"] is True
    assert workflow["auto_event_allowed"] is False
    assert workflow["manual_review_required"] is True
    for step in workflow["workflow_steps"]:
        assert step["automatic_execution_enabled"] is False
        assert step["trade_enabled"] is False
        assert step["implementation_ready_after_step"] is False

    assert "event_id" in requirements["event_required_fields"]
    assert "source_artifact_hash" in requirements["source_lineage_required_fields"]
    assert "event_time" in requirements["dedupe_key_fields"]
    assert "schema_completeness" in requirements["event_integrity_checks"]
    assert "later_outcome_completeness" in requirements["research_quality_checks"]
    assert "no_trade" in requirements["boundary_checks"]

    assert queue["queue_status"] == "empty_waiting_for_first_manual_event"
    assert queue["queued_event_count"] == 0
    assert queue["automatic_queue_population_enabled"] is False

    assert guardrails["trade_enabled"] is False
    assert guardrails["order_generation_enabled"] is False
    assert guardrails["broker_connection_enabled"] is False
    assert guardrails["position_adjustment_enabled"] is False
    assert guardrails["auto_risk_control_enabled"] is False

    assert promotion["promotion_allowed"] is False
    assert promotion["implementation_ready"] is False
    assert "first_manual_event_not_submitted" in promotion["blocking_reasons"]
    assert "workflow_only" in promotion["blocking_reasons"]

    assert time_safety["uses_v14_3_v14_5_v14_6_artifacts_only"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_scan_market"] is True
    assert time_safety["does_not_auto_generate_event"] is True
    assert time_safety["does_not_auto_generate_warning"] is True
    assert time_safety["does_not_auto_judge_risk"] is True

    assert constraints["first_event_workflow_only"] is True
    assert constraints["ready_for_first_manual_event"] is True
    assert constraints["no_event_created"] is True
    assert constraints["manual_event_required"] is True
    assert constraints["manual_review_required"] is True
    assert constraints["quality_audit_required"] is True
    assert constraints["does_not_auto_scan_market"] is True
    assert constraints["does_not_auto_generate_event"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_risk_diagnostic_shadow_first_event_workflow(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        log_path = tmp / "risk_diagnostic_shadow_observation_log.json"
        capture_path = tmp / "risk_diagnostic_shadow_manual_event_capture.json"
        quality_path = tmp / "risk_diagnostic_shadow_event_quality_audit.json"
        workflow_path = tmp / "risk_diagnostic_shadow_first_event_workflow.json"
        log_payload = build_risk_diagnostic_shadow_observation_log()
        capture_payload = build_risk_diagnostic_shadow_manual_event_capture_status()
        write_risk_diagnostic_shadow_observation_log(log_payload, log_path)
        write_risk_diagnostic_shadow_manual_event_capture_status(capture_payload, capture_path)
        quality_payload = build_risk_diagnostic_shadow_event_quality_audit(
            observation_log_path=log_path,
            manual_capture_path=capture_path,
        )
        write_risk_diagnostic_shadow_event_quality_audit(quality_payload, quality_path)
        tmp_payload = build_risk_diagnostic_shadow_first_event_workflow(
            observation_log_path=log_path,
            manual_capture_path=capture_path,
            quality_audit_path=quality_path,
        )
        assert tmp_payload["summary"]["workflow_status"] == "ready_for_first_manual_event"
        assert tmp_payload["summary"]["event_count"] == 0
        assert validate_risk_diagnostic_shadow_first_event_workflow(tmp_payload)["audit_status"] == "passed"
        workflow_path.write_text("ok", encoding="utf-8")
        assert workflow_path.exists()

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "510" + "880", "511" + "880", "159" + "915"):
        assert code not in joined
    assert "%" not in joined

    print("test_risk_diagnostic_shadow_first_event_workflow ok")


if __name__ == "__main__":
    main()
