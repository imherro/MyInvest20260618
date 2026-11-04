from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_evidence_dashboard,
    build_risk_diagnostic_shadow_event_quality_audit,
    build_risk_diagnostic_shadow_first_event_workflow,
    build_risk_diagnostic_shadow_manual_event_capture_status,
    build_risk_diagnostic_shadow_observation_log,
    build_risk_diagnostic_shadow_observation_review,
    validate_risk_diagnostic_shadow_evidence_dashboard,
    write_risk_diagnostic_shadow_evidence_dashboard,
    write_risk_diagnostic_shadow_event_quality_audit,
    write_risk_diagnostic_shadow_first_event_workflow,
    write_risk_diagnostic_shadow_manual_event_capture_status,
    write_risk_diagnostic_shadow_observation_log,
    write_risk_diagnostic_shadow_observation_review,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_evidence_dashboard()
    metadata = payload["metadata"]
    summary = payload["summary"]
    stats = payload["event_statistics"]
    status = payload["evidence_status"]
    gate = payload["implementation_gate"]
    guardrails = payload["no_trade_guardrails"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V14.9 Risk Diagnostic Shadow Evidence Accumulation Dashboard"
    assert len(metadata["input_hashes"]) == 5
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["component_id"] == "risk_diagnostic_layer"
    assert summary["dashboard_status"] == "ready"
    assert summary["dashboard_only"] is True
    assert summary["evidence_accumulation_status"] == "waiting_for_manual_events"
    assert summary["event_count"] == 0
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["implementation_ready"] is False
    assert summary["trade_enabled"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False

    assert stats["event_count"] == 0
    assert stats["validated_event_count"] == 0
    assert stats["pending_review_count"] == 0
    assert stats["reviewed_count"] == 0
    assert stats["false_warning_count"] == 0
    assert stats["missed_risk_count"] == 0
    assert stats["quality_queue_count"] == 0

    assert status["shadow_status"] == "active_empty"
    assert status["manual_capture_status"] == "ready_for_manual_input"
    assert status["review_status"] == "no_events_available"
    assert status["quality_audit_status"] == "no_events_available"
    assert status["first_event_workflow_status"] == "ready_for_first_manual_event"
    assert status["evidence_accumulation_status"] == "waiting_for_manual_events"

    assert gate["implementation_ready"] is False
    assert gate["trade_enabled"] is False
    assert "dashboard_only" in gate["blocking_reasons"]

    assert guardrails["trade_enabled"] is False
    assert guardrails["order_generation_enabled"] is False
    assert guardrails["broker_connection_enabled"] is False
    assert guardrails["position_adjustment_enabled"] is False
    assert guardrails["auto_risk_control_enabled"] is False

    assert time_safety["uses_existing_shadow_artifacts_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_scan_market"] is True
    assert time_safety["does_not_generate_event"] is True
    assert time_safety["does_not_generate_warning"] is True
    assert time_safety["does_not_judge_risk"] is True

    assert constraints["dashboard_only"] is True
    assert constraints["does_not_generate_event"] is True
    assert constraints["does_not_scan_market"] is True
    assert constraints["does_not_judge_risk"] is True
    assert constraints["does_not_adjust_exposure"] is True
    assert constraints["does_not_generate_strategy"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_allocate"] is True
    assert constraints["does_not_trade"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_risk_diagnostic_shadow_evidence_dashboard(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        log_path = tmp / "risk_diagnostic_shadow_observation_log.json"
        capture_path = tmp / "risk_diagnostic_shadow_manual_event_capture.json"
        review_path = tmp / "risk_diagnostic_shadow_observation_review.json"
        quality_path = tmp / "risk_diagnostic_shadow_event_quality_audit.json"
        workflow_path = tmp / "risk_diagnostic_shadow_first_event_workflow.json"
        dashboard_path = tmp / "risk_diagnostic_shadow_evidence_dashboard.json"
        log_payload = build_risk_diagnostic_shadow_observation_log()
        write_risk_diagnostic_shadow_observation_log(log_payload, log_path)
        capture_payload = build_risk_diagnostic_shadow_manual_event_capture_status(observation_log_path=log_path)
        write_risk_diagnostic_shadow_manual_event_capture_status(capture_payload, capture_path)
        review_payload = build_risk_diagnostic_shadow_observation_review(observation_log_path=log_path)
        write_risk_diagnostic_shadow_observation_review(review_payload, review_path)
        quality_payload = build_risk_diagnostic_shadow_event_quality_audit(
            observation_log_path=log_path,
            manual_capture_path=capture_path,
        )
        write_risk_diagnostic_shadow_event_quality_audit(quality_payload, quality_path)
        workflow_payload = build_risk_diagnostic_shadow_first_event_workflow(
            observation_log_path=log_path,
            manual_capture_path=capture_path,
            quality_audit_path=quality_path,
        )
        write_risk_diagnostic_shadow_first_event_workflow(workflow_payload, workflow_path)
        tmp_payload = build_risk_diagnostic_shadow_evidence_dashboard(
            observation_log_path=log_path,
            manual_capture_path=capture_path,
            observation_review_path=review_path,
            quality_audit_path=quality_path,
            first_event_workflow_path=workflow_path,
        )
        output = write_risk_diagnostic_shadow_evidence_dashboard(tmp_payload, dashboard_path)
        assert output.exists()
        assert tmp_payload["event_statistics"]["event_count"] == 0
        assert validate_risk_diagnostic_shadow_evidence_dashboard(tmp_payload)["audit_status"] == "passed"

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "510" + "880", "511" + "880", "159" + "915"):
        assert code not in joined
    assert "%" not in joined

    print("test_risk_diagnostic_shadow_evidence_dashboard ok")


if __name__ == "__main__":
    main()
