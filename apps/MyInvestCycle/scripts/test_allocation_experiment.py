from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_experiment_runner import (
    build_allocation_experiment_results,
    validate_allocation_experiment_results,
    write_allocation_experiment_results,
)


def main() -> None:
    payload = build_allocation_experiment_results()
    metadata = payload["metadata"]
    summary = payload["summary"]
    schema = payload["schema"]
    execution_scope = payload["execution_scope"]
    experiment_results = payload["experiment_results"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V9.5 Allocation Research Experiment Execution Phase 0"
    assert summary["source_context"] == "risk_controlled_opportunity_watch"
    assert summary["executed_experiment_count"] == 4
    assert summary["validation_result_count"] == 4
    assert summary["design_pass_count"] == 4
    assert summary["design_fail_count"] == 0
    assert summary["market_validation_result_count"] == 0
    assert summary["ready_for_asset_selection"] is False
    assert summary["ready_for_etf_mapping"] is False
    assert summary["ready_for_weight_generation"] is False
    assert summary["ready_for_backtest"] is False
    assert summary["ready_for_optimization"] is False
    assert summary["ready_for_trade"] is False
    assert summary["promoted_to_candidate"] is False
    assert summary["investable_output_generated"] is False
    assert summary["conclusion"] == "allocation_experiment_phase0_completed_research_only_not_investable"

    forbidden = set(schema["forbidden_outputs"])
    assert "asset_selection" in forbidden
    assert "etf_mapping" in forbidden
    assert "portfolio_weight" in forbidden
    assert "exposure_percent" in forbidden
    assert "backtest_result" in forbidden
    assert "optimization" in forbidden

    assert execution_scope["phase"] == "phase0_design_execution"
    assert execution_scope["market_data_loaded"] is False
    assert execution_scope["performance_measured"] is False
    assert execution_scope["parameter_search_performed"] is False
    assert execution_scope["candidate_promotion_allowed"] is False

    for result in experiment_results:
        assert result["execution_status"] == "completed"
        assert result["validation_result"] == "design_pass_market_not_evaluated"
        assert result["promotion_status"] == "not_promoted"
        assert result["investable_output"] is False
        joined = " ".join(str(value) for value in result.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert time_safety["uses_v9_4_artifact_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["future_returns_not_used"] is True
    assert time_safety["market_data_not_loaded"] is True
    assert data_quality["no_asset_data_loaded"] is True
    assert data_quality["no_etf_data_loaded"] is True
    assert data_quality["no_market_data_loaded"] is True
    assert data_quality["no_backtest"] is True
    assert data_quality["no_parameter_scan"] is True
    assert data_quality["no_optimization"] is True
    assert constraints["research_only"] is True
    assert constraints["phase0_execution_only"] is True
    assert constraints["uses_predeclared_templates_only"] is True
    assert constraints["does_not_load_market_data"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_exposure_percent"] is True
    assert constraints["does_not_run_backtest"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["no_buy_sell_signal"] is True
    assert constraints["no_rebalance_instruction"] is True
    assert audit["audit_status"] == "passed"
    assert validate_allocation_experiment_results(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_allocation_experiment_results(
            payload,
            Path(tmpdir) / "allocation_experiment_results_phase0.json",
        )
        assert output.exists()

    print("test_allocation_experiment ok")


if __name__ == "__main__":
    main()
