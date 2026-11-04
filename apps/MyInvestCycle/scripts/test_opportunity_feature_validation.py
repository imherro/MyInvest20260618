from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_feature_validation import (
    FEATURE_DEFINITIONS,
    HORIZONS,
    build_opportunity_feature_validation,
    write_opportunity_feature_validation,
)


def main() -> None:
    payload = build_opportunity_feature_validation()
    metadata = payload["metadata"]
    summary = payload["summary"]
    results = payload["feature_results"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert metadata["engine"] == "V7.3 Opportunity Feature Effectiveness Audit"
    assert summary["feature_count"] == len(FEATURE_DEFINITIONS)
    assert summary["horizons"] == list(HORIZONS)
    assert summary["context_observation_count"] > 30
    assert summary["result_count"] == len(FEATURE_DEFINITIONS) * len(HORIZONS)
    assert summary["ready_for_scoring"] is False
    assert summary["ready_for_ranking"] is False
    assert summary["ready_for_allocation"] is False
    assert summary["ready_for_trade"] is False

    expected_keys = {key for _, _, key in FEATURE_DEFINITIONS}
    assert {result["feature_key"] for result in results} == expected_keys
    for result in results:
        assert result["horizon_sessions"] in HORIZONS
        assert result["interpretation"] == "feature_validation_only_not_a_score_or_rank"
        for source_key in ("research_proxy", "tradable_etf"):
            source = result[source_key]
            assert source["status"] in {"visible", "weak", "flat", "insufficient"}
            assert isinstance(source["regime_breakdown"], dict)
            assert "sample_count" in source
            if source["sample_count"]:
                assert -1 <= source["mean_ic"] <= 1

    assert "rank" not in summary
    assert "top_assets" not in summary
    assert "score" not in summary
    assert time_safety["feature_values_use_history_lte_signal_date"] is True
    assert time_safety["forward_returns_used_only_as_validation_labels"] is True
    assert time_safety["future_returns_not_used_in_feature_values"] is True
    assert time_safety["research_proxy_and_tradable_etf_validated_separately"] is True
    assert time_safety["future_labels_used_for_scoring"] is False
    assert data_quality["feature_definitions_fixed"] is True
    assert data_quality["horizons_fixed_by_design"] is True
    assert data_quality["no_scoring"] is True
    assert data_quality["no_ranking"] is True
    assert data_quality["no_top_n"] is True
    assert data_quality["no_allocation"] is True
    assert data_quality["no_parameter_optimization"] is True
    assert constraints["effectiveness_audit_only"] is True
    assert constraints["does_not_create_opportunity_score"] is True
    assert constraints["does_not_rank_assets"] is True
    assert constraints["does_not_select_top_assets"] is True
    assert constraints["no_trade_signal"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_opportunity_feature_validation(payload, Path(tmpdir) / "opportunity_feature_validation.json")
        assert output.exists()

    print("test_opportunity_feature_validation ok")


if __name__ == "__main__":
    main()
