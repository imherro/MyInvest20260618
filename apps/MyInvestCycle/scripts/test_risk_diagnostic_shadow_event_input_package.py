from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_event_input_package,
    build_risk_diagnostic_shadow_first_event_workflow,
    validate_risk_diagnostic_shadow_event_input_file,
    validate_risk_diagnostic_shadow_event_input_package,
    write_risk_diagnostic_shadow_event_input_package,
)


def _valid_event() -> dict[str, object]:
    return {
        "event_id": "manual_shadow_input_20260707_001",
        "event_time": "2026-07-07T15:30:00+08:00",
        "market_data_as_of": "20260707",
        "component_id": "risk_diagnostic_layer",
        "warning_event_type": "manual_input_validation_observation",
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
            "source_artifact_hash": "d" * 64,
            "event_schema_version": "v14.8",
            "created_by": "manual_operator",
        },
        "no_trade_observation": {
            "trade_enabled": False,
            "order_generation_enabled": False,
            "broker_connection_enabled": False,
            "position_adjustment_enabled": False,
        },
        "later_outcome_review": {
            "review_time": None,
            "review_window_id": None,
            "later_risk_outcome": None,
            "false_warning_review": None,
            "missed_risk_review": None,
            "stability_review_note": None,
        },
        "manual_review_state": "submitted_pending_later_outcome_review",
    }


def main() -> None:
    payload = build_risk_diagnostic_shadow_event_input_package()
    metadata = payload["metadata"]
    summary = payload["summary"]
    source = payload["source_first_event_workflow"]
    template = payload["event_template"]
    schema = payload["json_schema"]
    cli = payload["validation_cli"]
    interface = payload["manual_submission_interface"]
    result = payload["current_submission_result"]
    guardrails = payload["no_trade_guardrails"]
    promotion = payload["promotion_gate"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V14.8 Risk Diagnostic Shadow First Event Submission Input Package"
    assert len(metadata["input_hashes"]) == 1
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["component_id"] == "risk_diagnostic_layer"
    assert summary["template_status"] == "ready"
    assert summary["event_submitted"] is False
    assert summary["validated_event_count"] == 0
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

    assert source["source_workflow_status"] == "ready_for_first_manual_event"
    assert source["source_event_count"] == 0
    assert source["source_quality_queue_count"] == 0
    assert source["source_trade_enabled"] is False
    assert len(source["source_hash"]) == 64

    assert template["component_id"] == "risk_diagnostic_layer"
    assert template["no_trade_observation"]["trade_enabled"] is False
    assert template["no_trade_observation"]["order_generation_enabled"] is False
    assert template["later_outcome_review"]["review_time"] is None

    assert schema["schema_version"] == "v14.8"
    assert set(schema["required"]) == {
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
    }

    assert cli["validates_only"] is True
    assert cli["append_to_log_enabled"] is False
    assert cli["requires_explicit_event_file"] is True
    assert interface["interface_status"] == "template_and_cli_ready"
    assert interface["web_upload_enabled"] is False
    assert interface["manual_submit_requires_explicit_user_approval"] is True

    assert result["event_file_supplied"] is False
    assert result["validation_status"] == "no_event_file_supplied"
    assert result["event_submitted"] is False
    assert result["validated_event_count"] == 0

    assert guardrails["trade_enabled"] is False
    assert guardrails["order_generation_enabled"] is False
    assert guardrails["broker_connection_enabled"] is False
    assert guardrails["position_adjustment_enabled"] is False
    assert guardrails["auto_risk_control_enabled"] is False

    assert promotion["promotion_allowed"] is False
    assert promotion["implementation_ready"] is False
    assert "first_manual_event_not_submitted" in promotion["blocking_reasons"]

    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_scan_market"] is True
    assert time_safety["does_not_auto_generate_event"] is True
    assert time_safety["does_not_auto_judge_risk"] is True

    assert constraints["event_input_package_only"] is True
    assert constraints["template_ready"] is True
    assert constraints["event_submitted_false"] is True
    assert constraints["validation_cli_only"] is True
    assert constraints["does_not_append_event"] is True
    assert constraints["does_not_auto_scan_market"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_risk_diagnostic_shadow_event_input_package(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        package_path = tmp / "risk_diagnostic_shadow_event_input_package.json"
        template_path = tmp / "risk_diagnostic_shadow_event_input_template.json"
        output, template_output = write_risk_diagnostic_shadow_event_input_package(
            payload,
            output_path=package_path,
            template_path=template_path,
        )
        assert output.exists()
        assert template_output.exists()

        event_path = tmp / "manual_event.json"
        event_path.write_text(json.dumps(_valid_event(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = validate_risk_diagnostic_shadow_event_input_file(event_path)
        assert validation["validation_status"] == "valid_not_submitted"
        assert validation["event_submitted"] is False
        assert validation["trade_enabled"] is False
        assert validation["implementation_ready"] is False

        command = [
            sys.executable,
            str(ROOT_DIR / "scripts" / "validate_risk_diagnostic_shadow_event_input.py"),
            "--event-file",
            str(event_path),
        ]
        completed = subprocess.run(command, cwd=ROOT_DIR, text=True, capture_output=True, check=True)
        cli_result = json.loads(completed.stdout)
        assert cli_result["validation_status"] == "valid_not_submitted"
        assert cli_result["event_submitted"] is False

        rejected = _valid_event()
        rejected["event_id"] = "manual_shadow_input_rejected"
        rejected["no_trade_observation"] = {
            "trade_enabled": True,
            "order_generation_enabled": False,
            "broker_connection_enabled": False,
            "position_adjustment_enabled": False,
        }
        rejected_path = tmp / "rejected_event.json"
        rejected_path.write_text(json.dumps(rejected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rejected_validation = validate_risk_diagnostic_shadow_event_input_file(rejected_path)
        assert rejected_validation["validation_status"] == "invalid_event_file"
        assert rejected_validation["event_submitted"] is False
        assert rejected_validation["trade_enabled"] is False

    workflow = build_risk_diagnostic_shadow_first_event_workflow()
    assert workflow["summary"]["event_count"] == 0

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "510" + "880", "511" + "880", "159" + "915"):
        assert code not in joined
    assert "%" not in joined

    print("test_risk_diagnostic_shadow_event_input_package ok")


if __name__ == "__main__":
    main()
