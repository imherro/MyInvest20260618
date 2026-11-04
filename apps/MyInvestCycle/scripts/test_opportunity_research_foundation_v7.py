from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_research_foundation import (
    build_opportunity_research_foundation,
    write_opportunity_research_foundation,
)


def main() -> None:
    payload = build_opportunity_research_foundation()
    metadata = payload["metadata"]
    summary = payload["summary"]
    coverage = payload["coverage"]
    rows = payload["asset_rows"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert metadata["engine"] == "V7.1 Opportunity / Asset Research Layer Foundation"
    assert summary["asset_count"] == 17
    assert summary["enabled_assets"] == 17
    assert summary["category_counts"]["industry"] >= 10
    assert summary["research_proxy_assets"] == 10
    assert summary["research_proxy_count"] >= 8
    assert summary["direct_history_only_assets"] == 7
    assert summary["research_proxy_full_window"] is True
    assert summary["tradable_history_full_window"] is False
    assert summary["readiness"] == "research_ready_with_tradability_caveat"
    assert summary["ready_for_scoring"] is False
    assert summary["ready_for_ranking"] is False
    assert summary["ready_for_allocation"] is False
    assert summary["ready_for_trade"] is False

    assert coverage["tradable_history"]["coverage_start"] == "20210204"
    assert coverage["tradable_history"]["target_window_fully_covered"] is False
    assert coverage["tradable_history"]["target_blocker_count"] > 0
    assert coverage["research_proxy_history"]["coverage_start"] == "20150105"
    assert coverage["research_proxy_history"]["target_window_fully_covered"] is True
    assert coverage["research_proxy_history"]["missing_proxy"] == []

    assert len(rows) == 17
    assert any(row["research_proxy"]["has_proxy"] for row in rows)
    assert any(row["research_proxy"]["has_proxy"] is False for row in rows)
    for row in rows:
        assert row["asset_type"] == "etf"
        assert row["enabled"] is True
        assert row["research_only"] is True

    assert time_safety["future_labels_used"] is False
    assert time_safety["research_proxy_not_treated_as_tradable"] is True
    assert time_safety["tradable_history_and_research_proxy_are_separated"] is True
    assert data_quality["no_scoring"] is True
    assert data_quality["no_ranking"] is True
    assert data_quality["no_allocation"] is True
    assert data_quality["no_backtest"] is True
    assert constraints["foundation_only"] is True
    assert constraints["does_not_create_opportunity_score"] is True
    assert constraints["does_not_rank_assets"] is True
    assert constraints["does_not_generate_position"] is True
    assert constraints["no_trade_signal"] is True
    assert constraints["no_broker_connection"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_opportunity_research_foundation(payload, Path(tmpdir) / "opportunity_research_foundation.json")
        assert output.exists()

    print("test_opportunity_research_foundation_v7 ok")


if __name__ == "__main__":
    main()
