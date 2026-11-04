from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_experiment_audit import (
    build_allocation_experiment_templates,
    validate_allocation_experiment_templates,
    write_allocation_experiment_templates,
)


def main() -> None:
    payload = build_allocation_experiment_templates()
    metadata = payload["metadata"]
    summary = payload["summary"]
    schema = payload["schema"]
    templates = payload["experiment_templates"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V9.4 Allocation Research Experiment Template Framework"
    assert summary["source_context"] == "risk_controlled_opportunity_watch"
    assert summary["experiment_template_count"] == 4
    assert summary["executed_experiment_count"] == 0
    assert summary["experiment_template_ready"] is False
    assert summary["experiment_executed"] is False
    assert summary["ready_for_asset_selection"] is False
    assert summary["ready_for_etf_mapping"] is False
    assert summary["ready_for_weight_generation"] is False
    assert summary["ready_for_backtest"] is False
    assert summary["ready_for_validation_result"] is False
    assert summary["ready_for_optimization"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "allocation_experiment_templates_defined_not_executed"

    forbidden = set(schema["forbidden_outputs"])
    assert "asset_selection" in forbidden
    assert "etf_mapping" in forbidden
    assert "portfolio_weight" in forbidden
    assert "exposure_percent" in forbidden
    assert "backtest_result" in forbidden
    assert "validation_result" in forbidden
    assert "experiment_result" in forbidden
    assert "optimization" in forbidden

    required_criteria = set(schema["required_evaluation_criteria"])
    for template in templates:
        assert template["execution_status"] == "template_only_not_executed"
        assert required_criteria.issubset(set(template["evaluation_criteria"]))
        comparison = template["predefined_comparison"]
        assert comparison["baseline"] == "baseline_research_posture"
        assert comparison["alternative"] == "alternative_research_posture"
        joined = " ".join(str(value) for value in template.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert time_safety["uses_v9_3_artifact_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["future_returns_not_used"] is True
    assert time_safety["experiment_not_executed"] is True
    assert data_quality["no_asset_data_loaded"] is True
    assert data_quality["no_etf_data_loaded"] is True
    assert data_quality["no_backtest"] is True
    assert data_quality["no_parameter_scan"] is True
    assert data_quality["no_optimization"] is True
    assert data_quality["no_validation_result"] is True
    assert data_quality["no_experiment_result"] is True
    assert constraints["research_only"] is True
    assert constraints["template_only"] is True
    assert constraints["does_not_execute_experiment"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_exposure_percent"] is True
    assert constraints["does_not_run_backtest"] is True
    assert constraints["does_not_generate_result"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["no_buy_sell_signal"] is True
    assert constraints["no_rebalance_instruction"] is True
    assert audit["audit_status"] == "passed"
    assert validate_allocation_experiment_templates(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_allocation_experiment_templates(
            payload,
            Path(tmpdir) / "allocation_experiment_templates.json",
        )
        assert output.exists()

    print("test_allocation_experiment_template ok")


if __name__ == "__main__":
    main()
