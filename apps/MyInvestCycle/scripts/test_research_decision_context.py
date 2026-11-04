from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from decision_research.research_decision_audit import audit_research_decision_context
from decision_research.research_decision_context import (
    build_research_decision_context,
    write_research_decision_context,
)


def main() -> None:
    payload = build_research_decision_context()
    metadata = payload["metadata"]
    summary = payload["summary"]
    research_context = payload["research_context"]
    opportunity = payload["opportunity_context_evidence"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V8.1 Research Decision Integration Architecture"
    assert summary["decision_context"] == "risk_controlled_opportunity_watch"
    assert summary["research_posture"] == "observe_without_selection"
    assert summary["risk_context_status"] == "risk_axis_visible_opportunity_axis_weak"
    assert summary["opportunity_context_status"] == "feature_attribution_not_ready_for_opportunity_score"
    assert summary["opportunity_research_candidate_count"] == 1
    assert summary["opportunity_watch_count"] == 17
    assert summary["ready_for_scoring"] is False
    assert summary["ready_for_ranking"] is False
    assert summary["ready_for_allocation"] is False
    assert summary["ready_for_trade"] is False

    assert research_context["context"] == "risk_controlled_opportunity_watch"
    assert research_context["research_posture"] == "observe_without_selection"
    assert "asset" not in research_context
    assert "rank" not in research_context
    assert "weight" not in research_context

    attention = opportunity["feature_group_attention"]
    assert isinstance(attention, list)
    assert len(attention) >= 1
    assert all("feature_group" in row for row in attention)
    assert all(row["interpretation"] == "feature_group_attention_only_not_asset_selection" for row in attention)

    assert time_safety["uses_existing_v6_outputs_only"] is True
    assert time_safety["uses_existing_v7_outputs_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert data_quality["uses_frozen_v6_artifacts_only"] is True
    assert data_quality["uses_frozen_v7_artifacts_only"] is True
    assert data_quality["no_new_feature_search"] is True
    assert data_quality["no_scoring"] is True
    assert data_quality["no_ranking"] is True
    assert data_quality["no_top_n"] is True
    assert data_quality["no_allocation"] is True
    assert data_quality["no_backtest"] is True
    assert constraints["research_only"] is True
    assert constraints["does_not_create_opportunity_score"] is True
    assert constraints["does_not_rank_assets"] is True
    assert constraints["does_not_select_top_assets"] is True
    assert constraints["no_etf_code"] is True
    assert constraints["no_trade_signal"] is True
    assert audit["audit_status"] == "passed"
    assert audit_research_decision_context(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_research_decision_context(payload, Path(tmpdir) / "research_decision_context.json")
        assert output.exists()

    print("test_research_decision_context ok")


if __name__ == "__main__":
    main()
