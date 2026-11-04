from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    append_no_trade_observation_event,
    build_risk_diagnostic_shadow_observation_log,
    validate_risk_diagnostic_shadow_observation_log,
    write_risk_diagnostic_shadow_observation_log,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_observation_log()
    metadata = payload["metadata"]
    summary = payload["summary"]
    source = payload["source_shadow_framework"]
    controls = payload["observation_controls"]
    schema = payload["event_schema_snapshot"]
    log = payload["shadow_observation_log"]
    guardrails = payload["no_trade_guardrails"]
    promotion = payload["promotion_gate"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V14.3 Risk Diagnostic Shadow Observation Log Initialization"
    assert len(metadata["input_hashes"]) == 1
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["component_id"] == "risk_diagnostic_layer"
    assert summary["observation_status"] == "active"
    assert summary["log_status"] == "active_empty"
    assert summary["event_count"] == 0
    assert summary["live_event_count"] == 0
    assert summary["manual_append_only"] is True
    assert summary["auto_trigger_enabled"] is False
    assert summary["trade_enabled"] is False
    assert summary["position_adjustment_enabled"] is False
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False
    assert summary["conclusion"] == "risk_diagnostic_shadow_log_active_empty_no_trade"

    assert source["source_shadow_framework_status"] == "defined"
    assert source["source_shadow_status"] == "planned"
    assert source["source_trade_enabled"] is False
    assert source["source_implementation_ready"] is False
    assert len(source["source_hash"]) == 64

    assert controls["append_mode"] == "manual_only"
    assert controls["auto_warning_detection_enabled"] is False
    assert controls["market_data_reader_enabled"] is False
    assert controls["requires_market_data_freeze_before_append"] is True
    assert controls["requires_source_hash_before_append"] is True
    assert controls["requires_no_trade_guardrails_before_append"] is True
    assert len(controls["dedupe_key_fields"]) == 4

    assert schema["schema_source"] == "v14_2_shadow_framework"
    assert schema["required_event_field_count"] == len(schema["required_event_fields"])
    assert "no_trade_observation" in schema["required_event_fields"]

    assert log["log_id"] == "risk_diagnostic_shadow_observation_log"
    assert log["component_id"] == "risk_diagnostic_layer"
    assert log["log_status"] == "active_empty"
    assert log["event_count"] == 0
    assert log["live_event_count"] == 0
    assert log["events"] == []

    assert guardrails["trade_enabled"] is False
    assert guardrails["order_generation_enabled"] is False
    assert guardrails["broker_connection_enabled"] is False
    assert guardrails["position_adjustment_enabled"] is False
    assert guardrails["auto_risk_control_enabled"] is False

    assert promotion["promotion_allowed"] is False
    assert promotion["implementation_ready"] is False
    assert "event_count_zero" in promotion["blocking_reasons"]
    assert "log_records_observation_only" in promotion["blocking_reasons"]

    assert time_safety["uses_v14_2_shadow_framework_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_auto_trigger_warning"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["observation_log_initialization_only"] is True
    assert constraints["active_empty_log_only"] is True
    assert constraints["manual_append_only"] is True
    assert constraints["does_not_auto_trigger_warning"] is True
    assert constraints["does_not_enable_auto_risk_control"] is True
    assert constraints["does_not_adjust_position"] is True
    assert constraints["does_not_adjust_exposure"] is True
    assert constraints["does_not_generate_strategy"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True

    rejected_event = {
        "event_id": "synthetic_reject_case",
        "event_time": "future_observation_time",
        "market_data_as_of": "future_data_date",
        "component_id": "risk_diagnostic_layer",
        "warning_event_type": "future_warning_candidate",
        "context_snapshot": {},
        "source_lineage": {},
        "no_trade_observation": {
            "trade_enabled": True,
            "order_generation_enabled": False,
            "broker_connection_enabled": False,
            "position_adjustment_enabled": False,
        },
        "later_outcome_review": {},
        "manual_review_state": "future_manual_review_required",
    }
    try:
        append_no_trade_observation_event(payload, rejected_event)
    except ValueError as exc:
        assert "no-trade guardrails" in str(exc)
    else:
        raise AssertionError("append helper must reject event with trade enabled")

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "510" + "880", "511" + "880", "159" + "915"):
        assert code not in joined
    assert "%" not in joined
    assert audit["audit_status"] == "passed"
    assert validate_risk_diagnostic_shadow_observation_log(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_risk_diagnostic_shadow_observation_log(
            payload,
            Path(tmpdir) / "risk_diagnostic_shadow_observation_log.json",
        )
        assert output.exists()

    print("test_risk_diagnostic_shadow_observation_log ok")


if __name__ == "__main__":
    main()
