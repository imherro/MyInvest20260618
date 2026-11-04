from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_feature_attribution import (
    build_opportunity_feature_attribution,
    write_opportunity_feature_attribution,
)


def main() -> None:
    payload = build_opportunity_feature_attribution()
    metadata = payload["metadata"]
    summary = payload["summary"]
    rows = payload["feature_attribution"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert metadata["engine"] == "V7.4 Opportunity Feature Attribution & Stability Audit"
    assert summary["source_result_count"] == 42
    assert summary["attribution_count"] == 42
    assert summary["source_result_count"] == len(rows)
    assert summary["ready_for_scoring"] is False
    assert summary["ready_for_ranking"] is False
    assert summary["ready_for_allocation"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "feature_attribution_not_ready_for_opportunity_score"
    assert sum(summary["retention_counts"].values()) == len(rows)

    for row in rows:
        assert row["retention"] in {"research_candidate", "watch", "reject_for_now", "insufficient"}
        assert row["proxy_etf_alignment"] in {"aligned", "both_flat", "one_side_only", "conflicting", "insufficient"}
        assert row["interpretation"] == "feature_attribution_only_not_a_score_or_weight"
        regime = row["regime_consistency"]
        assert regime["status"] in {
            "no_regime_signal",
            "consistent_context_signal",
            "single_context_signal",
            "mixed_or_conflicting_context_signal",
        }
        assert len(regime["regimes"]) == 4
        assert "score" not in row
        assert "rank" not in row
        assert "weight" not in row

    assert time_safety["uses_fixed_v7_3_validation_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert data_quality["source_result_count_matches_attribution"] is True
    assert data_quality["no_new_feature_search"] is True
    assert data_quality["no_scoring"] is True
    assert data_quality["no_feature_weighting"] is True
    assert data_quality["no_ranking"] is True
    assert data_quality["no_top_n"] is True
    assert data_quality["no_allocation"] is True
    assert constraints["does_not_create_opportunity_score"] is True
    assert constraints["does_not_create_feature_weight"] is True
    assert constraints["does_not_rank_assets"] is True
    assert constraints["does_not_select_top_assets"] is True
    assert constraints["no_trade_signal"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_opportunity_feature_attribution(payload, Path(tmpdir) / "opportunity_feature_attribution.json")
        assert output.exists()

    print("test_opportunity_feature_attribution ok")


if __name__ == "__main__":
    main()
