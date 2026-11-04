from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_research_final_boundary import (
    build_allocation_research_final_boundary,
    validate_allocation_research_final_boundary,
    write_allocation_research_final_boundary,
)


def main() -> None:
    payload = build_allocation_research_final_boundary()
    metadata = payload["metadata"]
    summary = payload["summary"]
    directions = payload["directions"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V10.3 Allocation Research Final Boundary Decision"
    assert len(metadata["input_hashes"]) == 2
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["research_phase_status"] == "completed"
    assert summary["direction_count"] == 4
    assert summary["continue_external_validation_count"] == 1
    assert summary["research_governance_only_count"] == 1
    assert summary["frozen_no_external_validation_count"] == 2
    assert summary["promotion_allowed"] is False
    assert summary["strategy_promotion"] is False
    assert summary["allocation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["investable_output_generated"] is False
    assert summary["ready_for_asset_selection"] is False
    assert summary["ready_for_etf_mapping"] is False
    assert summary["ready_for_weight_generation"] is False
    assert summary["ready_for_optimization"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "allocation_research_final_boundary_completed_no_strategy_no_allocation"

    assert set(directions) == {"H1", "H2", "H3", "H4"}
    assert directions["H1"]["status"] == "frozen_no_external_validation"
    assert directions["H2"]["status"] == "continue_external_validation"
    assert directions["H3"]["status"] == "frozen_no_external_validation"
    assert directions["H4"]["status"] == "research_governance_only"
    for row in directions.values():
        assert row["promotion_allowed"] is False
        assert row["strategy_promotion"] is False
        assert row["allocation_ready"] is False
        assert row["investable_output"] is False
        joined = " ".join(str(value) for value in row.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert time_safety["uses_v10_2_result_review_only"] is True
    assert time_safety["uses_v9_9_evidence_freeze_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_market_backtest"] is True
    assert time_safety["no_result_based_parameter_change"] is True
    assert constraints["research_only"] is True
    assert constraints["final_boundary_only"] is True
    assert constraints["uses_v10_2_result_review_only"] is True
    assert constraints["uses_v9_9_evidence_freeze_only"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_allocation_research_final_boundary(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_allocation_research_final_boundary(
            payload,
            Path(tmpdir) / "allocation_research_final_boundary.json",
        )
        assert output.exists()

    print("test_allocation_research_final_boundary ok")


if __name__ == "__main__":
    main()
