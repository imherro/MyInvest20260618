from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_validation_plan_audit import (
    build_allocation_validation_plan,
    validate_allocation_validation_plan,
    write_allocation_validation_plan,
)


def main() -> None:
    payload = build_allocation_validation_plan()
    metadata = payload["metadata"]
    summary = payload["summary"]
    schema = payload["schema"]
    validation_plans = payload["validation_plans"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V9.3 Allocation Research Validation Plan Framework"
    assert summary["source_context"] == "risk_controlled_opportunity_watch"
    assert summary["hypothesis_count"] == 4
    assert summary["validation_plan_count"] == 4
    assert summary["executed_plan_count"] == 0
    assert summary["validation_plan_ready"] is False
    assert summary["validation_executed"] is False
    assert summary["ready_for_asset_selection"] is False
    assert summary["ready_for_etf_mapping"] is False
    assert summary["ready_for_weight_generation"] is False
    assert summary["ready_for_backtest"] is False
    assert summary["ready_for_optimization"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "allocation_validation_plan_defined_not_executed"

    forbidden = set(schema["forbidden_outputs"])
    assert "asset_selection" in forbidden
    assert "etf_mapping" in forbidden
    assert "portfolio_weight" in forbidden
    assert "exposure_percent" in forbidden
    assert "backtest_result" in forbidden
    assert "optimization" in forbidden
    assert "validation_result" in forbidden

    required_evidence = set(schema["required_evidence"])
    anti_overfit = set(schema["required_anti_overfitting_rules"])
    for plan in validation_plans:
        assert plan["execution_status"] == "planned_not_executed"
        assert required_evidence.issubset(set(plan["required_evidence"]))
        assert anti_overfit.issubset(set(plan["anti_overfitting_rules"]))
        joined = " ".join(str(value) for value in plan.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert time_safety["uses_v9_2_artifact_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["future_returns_not_used"] is True
    assert time_safety["validation_not_executed"] is True
    assert data_quality["no_asset_data_loaded"] is True
    assert data_quality["no_etf_data_loaded"] is True
    assert data_quality["no_backtest"] is True
    assert data_quality["no_parameter_scan"] is True
    assert data_quality["no_optimization"] is True
    assert data_quality["no_validation_result"] is True
    assert constraints["research_only"] is True
    assert constraints["plan_only"] is True
    assert constraints["does_not_execute_validation"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_exposure_percent"] is True
    assert constraints["does_not_run_backtest"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["no_buy_sell_signal"] is True
    assert constraints["no_rebalance_instruction"] is True
    assert audit["audit_status"] == "passed"
    assert validate_allocation_validation_plan(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_allocation_validation_plan(
            payload,
            Path(tmpdir) / "allocation_validation_plan.json",
        )
        assert output.exists()

    print("test_allocation_validation_plan ok")


if __name__ == "__main__":
    main()
