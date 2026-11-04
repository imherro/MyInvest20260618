from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from external_validation.validation_execution_framework import (
    build_h2_external_validation_execution,
    validate_h2_external_validation_execution,
    write_h2_external_validation_execution,
)


def main() -> None:
    payload = build_h2_external_validation_execution()
    metadata = payload["metadata"]
    summary = payload["summary"]
    runs = payload["validation_runs"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V11.2 H2 External Validation Execution Framework"
    assert len(metadata["input_hashes"]) == 7
    for value in metadata["input_hashes"].values():
        assert len(value) == 64
    assert summary["execution_status"] == "completed"
    assert summary["target_hypothesis"] == "H2"
    assert summary["window_count"] == 4
    assert summary["passed_count"] == 1
    assert summary["failed_count"] == 0
    assert summary["inconclusive_count"] == 3
    assert summary["overall_status"] == "inconclusive"
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
    assert summary["conclusion"] == "h2_external_validation_inconclusive_no_strategy_no_allocation"

    statuses = {row["window_id"]: row["status"] for row in runs}
    assert statuses == {
        "holdout_recent_window": "inconclusive",
        "regime_transition_window": "inconclusive",
        "structural_bull_window": "inconclusive",
        "adverse_risk_window": "passed",
    }
    for row in runs:
        joined = " ".join(str(value) for value in row.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert time_safety["uses_v11_1_protocol"] is True
    assert time_safety["uses_v10_3_final_boundary"] is True
    assert time_safety["uses_frozen_risk_evidence_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_market_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["research_only"] is True
    assert constraints["external_validation_execution_only"] is True
    assert constraints["uses_v11_1_protocol"] is True
    assert constraints["uses_v10_3_final_boundary"] is True
    assert constraints["uses_frozen_risk_evidence_only"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_h2_external_validation_execution(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_h2_external_validation_execution(
            payload,
            Path(tmpdir) / "h2_external_validation_execution.json",
        )
        assert output.exists()

    print("test_h2_external_validation_execution ok")


if __name__ == "__main__":
    main()
