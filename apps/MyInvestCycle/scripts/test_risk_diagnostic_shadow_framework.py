from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow.observation_framework import (
    CONTEXT_SNAPSHOT_FIELDS,
    EVENT_REQUIRED_FIELDS,
    OUTCOME_REVIEW_FIELDS,
    build_risk_diagnostic_shadow_framework,
    validate_risk_diagnostic_shadow_framework,
    write_risk_diagnostic_shadow_framework,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_framework()
    metadata = payload["metadata"]
    summary = payload["summary"]
    source = payload["source_evidence_package"]
    schema = payload["event_log_schema"]
    template = payload["warning_event_template"]
    log = payload["shadow_observation_log"]
    guardrails = payload["no_trade_guardrails"]
    promotion = payload["promotion_gate"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V14.2 Risk Diagnostic Shadow Observation Framework"
    assert len(metadata["input_hashes"]) == 2
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["component_id"] == "risk_diagnostic_layer"
    assert summary["shadow_framework_status"] == "defined"
    assert summary["shadow_status"] == "planned"
    assert summary["observation_only"] is True
    assert summary["live_event_count"] == 0
    assert summary["trade_enabled"] is False
    assert summary["position_adjustment_enabled"] is False
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False
    assert summary["conclusion"] == "risk_diagnostic_shadow_framework_defined_observation_only_no_trade"

    assert source["component_id"] == "risk_diagnostic_layer"
    assert source["source_package_status"] == "submitted_blocked_phase_0"
    assert source["source_evidence_status"] == "submitted"
    assert source["source_implementation_ready"] is False
    assert source["source_shadow_observation_required"] is True
    assert len(source["source_hash"]) == 64

    assert schema["schema_status"] == "defined"
    assert set(schema["required_event_fields"]) == set(EVENT_REQUIRED_FIELDS)
    assert set(schema["context_snapshot_fields"]) == set(CONTEXT_SNAPSHOT_FIELDS)
    assert set(schema["later_outcome_review_fields"]) == set(OUTCOME_REVIEW_FIELDS)

    assert template["template_status"] == "defined_not_instantiated"
    assert template["component_id"] == "risk_diagnostic_layer"
    assert template["no_trade_observation"]["trade_enabled"] is False
    assert template["no_trade_observation"]["order_generation_enabled"] is False
    assert template["no_trade_observation"]["broker_connection_enabled"] is False
    assert template["no_trade_observation"]["position_adjustment_enabled"] is False

    assert log["log_status"] == "initialized_empty"
    assert log["component_id"] == "risk_diagnostic_layer"
    assert log["live_event_count"] == 0
    assert log["events"] == []

    assert guardrails["trade_enabled"] is False
    assert guardrails["order_generation_enabled"] is False
    assert guardrails["broker_connection_enabled"] is False
    assert guardrails["position_adjustment_enabled"] is False
    assert guardrails["auto_risk_control_enabled"] is False

    assert promotion["promotion_allowed"] is False
    assert promotion["implementation_ready"] is False
    assert "live_shadow_observation_log_missing" in promotion["blocking_reasons"]
    assert "manual_review_not_approved" in promotion["blocking_reasons"]

    assert time_safety["uses_v14_1_evidence_package_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_generate_warning_event"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["shadow_framework_only"] is True
    assert constraints["observation_only"] is True
    assert constraints["does_not_generate_warning_event"] is True
    assert constraints["does_not_enable_auto_risk_control"] is True
    assert constraints["does_not_adjust_position"] is True
    assert constraints["does_not_generate_strategy"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "510" + "880", "511" + "880", "159" + "915"):
        assert code not in joined
    assert "%" not in joined
    assert audit["audit_status"] == "passed"
    assert validate_risk_diagnostic_shadow_framework(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_risk_diagnostic_shadow_framework(
            payload,
            Path(tmpdir) / "risk_diagnostic_shadow_observation_framework.json",
        )
        assert output.exists()

    print("test_risk_diagnostic_shadow_framework ok")


if __name__ == "__main__":
    main()
