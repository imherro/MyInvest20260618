from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from decision_research.research_decision_contradiction import (
    build_research_decision_contradiction,
    write_research_decision_contradiction,
)


def main() -> None:
    payload = build_research_decision_contradiction()
    metadata = payload["metadata"]
    summary = payload["summary"]
    attributions = payload["attributions"]
    focus_policy = payload["focus_policy"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert metadata["engine"] == "V8.3 Research Decision Contradiction Attribution"
    assert summary["base_decision_context"] == "risk_controlled_opportunity_watch"
    assert summary["base_research_posture"] == "observe_without_selection"
    assert summary["scenario_count"] == 6
    assert summary["focus_scenario_count"] >= 4
    assert summary["attribution_count"] == len(attributions)
    assert summary["ready_for_scoring"] is False
    assert summary["ready_for_ranking"] is False
    assert summary["ready_for_allocation"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "contradiction_attribution_research_only_no_rule_change"

    assert focus_policy["included_when_consistency_low"] is True
    assert focus_policy["included_when_contradiction_count_positive"] is True
    assert focus_policy["always_include_structural_market"] is True
    assert "2018_bear" in focus_policy["primary_focus_scenarios"]
    assert "2015_bull_bear_transition" in focus_policy["primary_focus_scenarios"]
    assert "2024_2026_structural_market" in focus_policy["primary_focus_scenarios"]

    for row in attributions:
        assert row["scenario"]
        assert row["contradiction_type"]
        assert row["possible_reason"]
        assert row["confidence_level"] in {"low", "medium", "high"}
        assert row["research_only"] is True
        assert row["no_rule_change"] is True
        assert "rank" not in row
        assert "weight" not in row
        assert "position" not in row

    assert time_safety["uses_existing_v8_2_output_only"] is True
    assert time_safety["uses_existing_v8_1_output_only"] is True
    assert time_safety["uses_existing_v6_rows_only"] is True
    assert time_safety["uses_existing_v7_attribution_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert data_quality["fixed_attribution_rules"] is True
    assert data_quality["no_new_state"] is True
    assert data_quality["no_scoring"] is True
    assert data_quality["no_ranking"] is True
    assert data_quality["no_top_n"] is True
    assert data_quality["no_allocation"] is True
    assert data_quality["no_backtest"] is True
    assert constraints["attribution_only"] is True
    assert constraints["research_only"] is True
    assert constraints["does_not_modify_v6"] is True
    assert constraints["does_not_modify_v7"] is True
    assert constraints["does_not_add_state"] is True
    assert constraints["does_not_create_opportunity_score"] is True
    assert constraints["does_not_rank_assets"] is True
    assert constraints["does_not_select_top_assets"] is True
    assert constraints["no_etf_code"] is True
    assert constraints["no_trade_signal"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_research_decision_contradiction(
            payload,
            Path(tmpdir) / "research_decision_contradiction.json",
        )
        assert output.exists()

    print("test_research_decision_contradiction ok")


if __name__ == "__main__":
    main()
