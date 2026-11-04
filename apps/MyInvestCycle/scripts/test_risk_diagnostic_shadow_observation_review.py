from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow.observation_review import (
    REVIEW_CHECKS,
    build_risk_diagnostic_shadow_observation_review,
    validate_risk_diagnostic_shadow_observation_review,
    write_risk_diagnostic_shadow_observation_review,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_observation_review()
    metadata = payload["metadata"]
    summary = payload["summary"]
    source = payload["source_observation_log"]
    framework = payload["review_framework"]
    result = payload["review_result"]
    guardrails = payload["no_trade_guardrails"]
    promotion = payload["promotion_gate"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V14.4 Risk Diagnostic Shadow Observation Event Review Framework"
    assert len(metadata["input_hashes"]) == 1
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["component_id"] == "risk_diagnostic_layer"
    assert summary["review_framework_status"] == "defined"
    assert summary["review_status"] == "no_events_available"
    assert summary["event_count"] == 0
    assert summary["reviewed_event_count"] == 0
    assert summary["auto_review_enabled"] is False
    assert summary["auto_warning_enabled"] is False
    assert summary["trade_enabled"] is False
    assert summary["position_adjustment_enabled"] is False
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False
    assert summary["conclusion"] == "risk_diagnostic_shadow_review_no_events_no_trade"

    assert source["source_observation_status"] == "active"
    assert source["source_log_status"] == "active_empty"
    assert source["source_event_count"] == 0
    assert source["source_auto_trigger_enabled"] is False
    assert source["source_trade_enabled"] is False
    assert len(source["source_hash"]) == 64

    assert set(framework["review_checks"]) == set(REVIEW_CHECKS)
    assert framework["manual_review_required"] is True
    assert framework["auto_decision_allowed"] is False
    assert framework["requires_later_outcome_review"] is True
    assert framework["requires_false_warning_review"] is True
    assert framework["requires_missed_risk_review"] is True
    assert framework["requires_source_lineage"] is True

    assert result["review_status"] == "no_events_available"
    assert result["reviewed_event_count"] == 0
    assert result["event_reviews"] == []

    assert guardrails["trade_enabled"] is False
    assert guardrails["order_generation_enabled"] is False
    assert guardrails["broker_connection_enabled"] is False
    assert guardrails["position_adjustment_enabled"] is False
    assert guardrails["auto_risk_control_enabled"] is False

    assert promotion["promotion_allowed"] is False
    assert promotion["implementation_ready"] is False
    assert "no_shadow_events_available" in promotion["blocking_reasons"]
    assert "review_framework_only" in promotion["blocking_reasons"]

    assert time_safety["uses_v14_3_observation_log_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_auto_generate_warning"] is True
    assert time_safety["does_not_auto_review_events"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["review_framework_only"] is True
    assert constraints["no_events_available"] is True
    assert constraints["does_not_auto_generate_warning"] is True
    assert constraints["does_not_auto_judge_risk"] is True
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

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "510" + "880", "511" + "880", "159" + "915"):
        assert code not in joined
    assert "%" not in joined
    assert audit["audit_status"] == "passed"
    assert validate_risk_diagnostic_shadow_observation_review(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_risk_diagnostic_shadow_observation_review(
            payload,
            Path(tmpdir) / "risk_diagnostic_shadow_observation_review.json",
        )
        assert output.exists()

    print("test_risk_diagnostic_shadow_observation_review ok")


if __name__ == "__main__":
    main()
