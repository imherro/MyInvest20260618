from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from external_validation.validation_protocol_audit import (
    build_external_validation_protocol,
    validate_external_validation_protocol,
    write_external_validation_protocol,
)


def main() -> None:
    payload = build_external_validation_protocol()
    metadata = payload["metadata"]
    schema = payload["schema"]
    summary = payload["summary"]
    protocol = payload["protocol"]
    excluded = payload["excluded_directions"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V11.1 External Validation Research Protocol"
    assert len(metadata["input_hashes"]) == 1
    for value in metadata["input_hashes"].values():
        assert len(value) == 64
    assert schema["schema_version"] == "V11.1"
    assert summary["protocol_phase_status"] == "defined"
    assert summary["target_hypothesis"] == "H2"
    assert summary["target_direction_count"] == 1
    assert summary["excluded_direction_count"] == 3
    assert summary["protocol_ready_for_manual_external_validation"] is True
    assert summary["promotion_allowed"] is False
    assert summary["strategy_promotion"] is False
    assert summary["allocation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["investable_output_generated"] is False
    assert summary["ready_for_asset_selection"] is False
    assert summary["ready_for_etf_mapping"] is False
    assert summary["ready_for_weight_generation"] is False
    assert summary["ready_for_optimization"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "h2_external_validation_protocol_defined_no_strategy_no_allocation"

    assert protocol["hypothesis_id"] == "H2"
    assert protocol["source_status"] == "continue_external_validation"
    assert protocol["protocol_status"] == "pre_registered"
    assert len(protocol["validation_windows"]) == 4
    assert len(protocol["pre_registered_methods"]) == 4
    assert len(protocol["failure_standards"]) >= 4
    assert len(protocol["stop_conditions"]) >= 4
    assert set(excluded) == {"H1", "H3", "H4"}
    assert excluded["H4"]["protocol_role"] == "research_governance_only_not_prediction_validation"

    assert time_safety["uses_v10_3_final_boundary_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_market_backtest"] is True
    assert time_safety["does_not_run_external_validation"] is True
    assert time_safety["requires_pre_declared_windows_before_any_future_run"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["research_only"] is True
    assert constraints["external_validation_protocol_only"] is True
    assert constraints["uses_v10_3_final_boundary_only"] is True
    assert constraints["does_not_run_external_validation"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True

    joined_protocol = " ".join(str(value) for value in protocol.values())
    assert "510" not in joined_protocol
    assert "159" not in joined_protocol
    assert "%" not in joined_protocol
    assert audit["audit_status"] == "passed"
    assert validate_external_validation_protocol(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_external_validation_protocol(
            payload,
            Path(tmpdir) / "external_validation_protocol.json",
        )
        assert output.exists()

    print("test_external_validation_protocol ok")


if __name__ == "__main__":
    main()
