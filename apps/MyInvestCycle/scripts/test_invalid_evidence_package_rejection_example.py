from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.evidence_package_rejection_example import (
    build_invalid_evidence_package_rejection_example,
    validate_invalid_evidence_package_rejection_example,
    write_invalid_evidence_package_rejection_example,
)


def main() -> None:
    payload = build_invalid_evidence_package_rejection_example()
    metadata = payload["metadata"]
    summary = payload["summary"]
    example = payload["invalid_example_summary"]
    result = payload["validator_result"]
    source = payload["source_engine_evidence"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V13.3 Invalid Evidence Package Rejection Test"
    assert len(metadata["input_hashes"]) == 2
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["example_status"] == "generated"
    assert summary["example_package_kind"] == "invalid_blocked_case"
    assert summary["package_status"] == "invalid_missing_or_boundary_violation"
    assert summary["validation_decision"] == "blocked_pending_manual_review_and_future_audit"
    assert summary["missing_item_count"] >= 1
    assert summary["boundary_violation_count"] >= 2
    assert summary["forbidden_output_detected"] is True
    assert summary["market_code_pattern_found"] is False
    assert summary["implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False
    assert summary["conclusion"] == "invalid_evidence_package_rejected_no_strategy_no_allocation"

    assert example["package_id"] == "example_invalid_package"
    assert example["component_id"] == "allocation_alpha_layer"
    assert example["example_only"] is True
    assert example["contains_real_market_code"] is False
    assert example["contains_real_weight"] is False
    assert example["redacted_forbidden_field_present"] is True
    assert "missing_required_field" in example["detected_boundary_violations"]
    assert "forbidden_output_key_detected" in example["detected_boundary_violations"]

    assert result["package_present"] is True
    assert result["component_id_status"] == "valid"
    assert result["implementation_ready"] is False
    assert result["market_code_pattern_found"] is False
    assert "missing_required_field" in result["boundary_violations"]
    assert "forbidden_output_key_detected" in result["boundary_violations"]
    assert result["missing_items"]

    assert source["v13_2_validation_engine_status"] == "defined"
    assert source["v13_2_current_package_status"] == "invalid_not_submitted"
    assert source["v13_2_implementation_ready"] is False
    assert source["v13_1_protocol_status"] == "defined"

    assert time_safety["uses_v13_1_and_v13_2_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_compute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["uses_synthetic_invalid_package_only"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["invalid_example_only"] is True
    assert constraints["does_not_submit_real_evidence"] is True
    assert constraints["does_not_evaluate_strategy_return"] is True
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
    assert validate_invalid_evidence_package_rejection_example(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_invalid_evidence_package_rejection_example(
            payload,
            Path(tmpdir) / "invalid_evidence_package_rejection_example.json",
        )
        assert output.exists()

    print("test_invalid_evidence_package_rejection_example ok")


if __name__ == "__main__":
    main()
