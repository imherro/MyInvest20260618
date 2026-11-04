from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.research_candidate_deep_validation import (
    build_research_candidate_deep_validation,
    validate_research_candidate_deep_validation,
    write_research_candidate_deep_validation,
)


def main() -> None:
    payload = build_research_candidate_deep_validation()
    metadata = payload["metadata"]
    summary = payload["summary"]
    results = payload["deep_validation_results"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V9.8 Research Candidate Deep Validation Framework"
    assert summary["target_hypothesis_count"] == 2
    assert summary["validation_result_count"] == 2
    assert summary["supported_count"] == 1
    assert summary["inconclusive_count"] == 1
    assert summary["unsupported_count"] == 0
    assert summary["promotion_allowed"] is False
    assert summary["strategy_promotion"] is False
    assert summary["allocation_promotion"] is False
    assert summary["investable_output"] is False
    assert summary["investable_output_generated"] is False
    assert summary["ready_for_asset_selection"] is False
    assert summary["ready_for_etf_mapping"] is False
    assert summary["ready_for_weight_generation"] is False
    assert summary["ready_for_optimization"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "research_candidate_deep_validation_completed_research_only_no_strategy"

    result_by_id = {row["hypothesis_id"]: row for row in results}
    assert set(result_by_id) == {"H2", "H4"}
    assert result_by_id["H2"]["validation_depth"] == "extended"
    assert result_by_id["H2"]["status"] == "inconclusive"
    assert result_by_id["H2"]["deep_checks"]["strict_stability_pass"] is False
    assert result_by_id["H4"]["validation_depth"] == "extended"
    assert result_by_id["H4"]["status"] == "supported"
    assert result_by_id["H4"]["deep_checks"]["promotion_blocked"] is True

    for result in results:
        assert result["research_only"] is True
        assert result["source_gate_status"] == "continue_research"
        assert result["phase1_status"] == "supported"
        assert result["promotion_allowed"] is False
        assert result["strategy_promotion"] is False
        assert result["allocation_promotion"] is False
        assert result["investable_output"] is False
        joined = " ".join(str(value) for value in result.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert time_safety["uses_frozen_artifacts_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["no_result_based_parameter_change"] is True
    assert constraints["research_only"] is True
    assert constraints["deep_validation_only"] is True
    assert constraints["uses_frozen_artifacts_only"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_research_candidate_deep_validation(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_research_candidate_deep_validation(
            payload,
            Path(tmpdir) / "research_candidate_deep_validation.json",
        )
        assert output.exists()

    print("test_research_candidate_deep_validation ok")


if __name__ == "__main__":
    main()
