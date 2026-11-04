from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from decision_research.research_decision_scenario_audit import (
    SCENARIOS,
    build_research_decision_scenario_audit,
    write_research_decision_scenario_audit,
)


def main() -> None:
    payload = build_research_decision_scenario_audit()
    metadata = payload["metadata"]
    summary = payload["summary"]
    scenarios = payload["scenarios"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert metadata["engine"] == "V8.2 Research Decision Historical Scenario Audit"
    assert summary["base_decision_context"] == "risk_controlled_opportunity_watch"
    assert summary["base_research_posture"] == "observe_without_selection"
    assert summary["scenario_count"] == len(SCENARIOS)
    assert summary["covered_scenario_count"] >= 4
    assert summary["ready_for_scoring"] is False
    assert summary["ready_for_ranking"] is False
    assert summary["ready_for_allocation"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "scenario_explanation_audit_only_no_strategy"

    assert len(scenarios) == len(SCENARIOS)
    for row in scenarios:
        assert row["scenario"]
        assert row["research_only"] is True
        assert row["consistency"] in {"high", "medium", "low", "insufficient"}
        assert row["coverage_status"] in {"covered", "insufficient"}
        assert "two_axis_distribution" in row
        assert "market_phase_distribution" in row
        assert "return" not in row
        assert "rank" not in row
        assert "weight" not in row

    assert time_safety["uses_existing_v8_1_output_only"] is True
    assert time_safety["uses_existing_v6_rows_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_use_return_metrics"] is True
    assert data_quality["fixed_scenarios"] is True
    assert data_quality["no_scoring"] is True
    assert data_quality["no_ranking"] is True
    assert data_quality["no_top_n"] is True
    assert data_quality["no_allocation"] is True
    assert data_quality["no_backtest"] is True
    assert data_quality["no_return_metric"] is True
    assert constraints["audit_only"] is True
    assert constraints["research_only"] is True
    assert constraints["does_not_create_opportunity_score"] is True
    assert constraints["does_not_rank_assets"] is True
    assert constraints["does_not_select_top_assets"] is True
    assert constraints["no_etf_code"] is True
    assert constraints["no_trade_signal"] is True
    assert constraints["no_return_optimization"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_research_decision_scenario_audit(
            payload,
            Path(tmpdir) / "research_decision_scenario_audit.json",
        )
        assert output.exists()

    print("test_research_decision_scenario_audit ok")


if __name__ == "__main__":
    main()
