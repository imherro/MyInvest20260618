from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from external_validation.validation_result_freeze import (
    build_h2_external_validation_result_freeze,
    validate_h2_external_validation_result_freeze,
    write_h2_external_validation_result_freeze,
)


def main() -> None:
    payload = build_h2_external_validation_result_freeze()
    metadata = payload["metadata"]
    summary = payload["summary"]
    conclusion = payload["final_conclusion"]
    evidence = payload["evidence"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V11.3 H2 External Validation Result Freeze & Final Interpretation"
    assert len(metadata["input_hashes"]) == 1
    for value in metadata["input_hashes"].values():
        assert len(value) == 64
    assert summary["freeze_status"] == "frozen"
    assert summary["target_hypothesis"] == "H2"
    assert summary["h2_status"] == "inconclusive"
    assert summary["evidence_supported_count"] == 1
    assert summary["evidence_not_confirmed_count"] == 1
    assert summary["evidence_unresolved_count"] == 1
    assert summary["evidence_insufficient_count"] == 1
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
    assert summary["conclusion"] == "h2_external_validation_frozen_inconclusive_no_strategy_no_allocation"

    assert conclusion["H2_status"] == "inconclusive"
    assert conclusion["research_decision"] == "continue_observation_only"
    assert conclusion["promotion_allowed"] is False
    assert conclusion["strategy_promotion"] is False
    assert conclusion["allocation_ready"] is False
    assert conclusion["investable_output"] is False
    assert conclusion["ready_for_trade"] is False
    assert evidence["adverse_risk"]["status"] == "supported"
    assert evidence["cross_regime_stability"]["status"] == "not_confirmed"
    assert evidence["recent_holdout"]["status"] == "insufficient"
    assert evidence["structural_opportunity_conflict"]["status"] == "unresolved"

    assert time_safety["uses_v11_2_execution_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_market_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_change_thresholds"] is True
    assert time_safety["does_not_add_features"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["research_only"] is True
    assert constraints["result_freeze_only"] is True
    assert constraints["uses_v11_2_execution_only"] is True
    assert constraints["does_not_modify_h2"] is True
    assert constraints["does_not_modify_risk_gradient"] is True
    assert constraints["does_not_change_thresholds"] is True
    assert constraints["does_not_add_features"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True

    joined = " ".join(str(value) for value in payload.values())
    assert "510" not in joined
    assert "159" not in joined
    assert "%" not in joined
    assert audit["audit_status"] == "passed"
    assert validate_h2_external_validation_result_freeze(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_h2_external_validation_result_freeze(
            payload,
            Path(tmpdir) / "h2_external_validation_result_freeze.json",
        )
        assert output.exists()

    print("test_h2_external_validation_result_freeze ok")


if __name__ == "__main__":
    main()
