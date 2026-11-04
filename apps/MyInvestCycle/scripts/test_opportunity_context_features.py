from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_context_features import (
    build_opportunity_context_features,
    write_opportunity_context_features,
)


def _assert_feature(field: dict[str, object]) -> None:
    assert "value" in field
    assert field["source"]
    assert field["source_kind"] in {"etf", "research_proxy", "benchmark_etf", "market_context"}
    assert field["as_of"]
    assert field["method"]


def main() -> None:
    payload = build_opportunity_context_features()
    metadata = payload["metadata"]
    summary = payload["summary"]
    context = payload["environment_context"]
    rows = payload["assets"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert metadata["engine"] == "V7.2 Structural Opportunity Context Feature Audit"
    assert summary["asset_count"] == 17
    assert len(rows) == 17
    assert set(summary["feature_groups"]) == {"momentum", "relative_strength", "trend", "risk", "structure"}
    assert summary["source_counts"]["research_proxy"] == 10
    assert summary["source_counts"]["etf"] == 7
    assert summary["ready_for_scoring"] is False
    assert summary["ready_for_ranking"] is False
    assert summary["ready_for_allocation"] is False
    assert summary["ready_for_trade"] is False
    assert summary["resolved_as_of"] <= summary["requested_as_of"]

    assert context["not_used_for_asset_scoring"] is True
    assert context["not_used_for_asset_ranking"] is True
    assert context["not_used_for_allocation"] is True
    assert "layer_3_two_axis_context" in context["retained_layers"]

    for row in rows:
        assert "rank" not in row
        assert "score" not in row
        assert row["constraints"]["no_opportunity_score"] is True
        assert row["constraints"]["no_ranking"] is True
        assert row["constraints"]["no_top_n"] is True
        assert row["constraints"]["no_allocation"] is True
        assert row["constraints"]["no_trade_signal"] is True
        features = row["features"]
        for field in ("return_20d", "return_60d", "return_120d"):
            _assert_feature(features["momentum"][field])
        for field in ("relative_return_60d_vs_hs300", "relative_return_60d_vs_csi500"):
            _assert_feature(features["relative_strength"][field])
        for field in ("ma60", "ma120", "ma250", "distance_to_ma60", "distance_to_ma120", "distance_to_ma250"):
            _assert_feature(features["trend"][field])
        for field in ("volatility_60d_annualized", "max_drawdown_120d", "price_extension_252d_percentile"):
            _assert_feature(features["risk"][field])
        for field in ("industry_breadth", "theme_persistence", "crowding_score"):
            _assert_feature(features["structure"][field])

    completeness = summary["feature_completeness"]
    assert completeness["momentum"]["coverage"] == 1.0
    assert completeness["relative_strength"]["coverage"] == 1.0
    assert completeness["structure"]["coverage"] == 1.0

    assert time_safety["resolved_lte_requested"] is True
    assert time_safety["uses_only_history_lte_as_of"] is True
    assert time_safety["future_labels_used"] is False
    assert time_safety["research_proxy_not_treated_as_tradable"] is True
    assert time_safety["v6_context_reference_not_used_for_asset_ranking"] is True
    assert time_safety["v6_context_metadata_only"] is True
    assert time_safety["v6_context_values_not_joined_to_asset_features"] is True
    assert data_quality["no_scoring"] is True
    assert data_quality["no_ranking"] is True
    assert data_quality["no_top_n"] is True
    assert data_quality["no_allocation"] is True
    assert constraints["does_not_create_opportunity_score"] is True
    assert constraints["does_not_rank_assets"] is True
    assert constraints["does_not_select_top_assets"] is True
    assert constraints["no_trade_signal"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_opportunity_context_features(payload, Path(tmpdir) / "opportunity_context_features.json")
        assert output.exists()

    print("test_opportunity_context_features ok")


if __name__ == "__main__":
    main()
