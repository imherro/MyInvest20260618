from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_research_evidence_freeze import (
    build_allocation_research_evidence_freeze,
    validate_allocation_research_evidence_freeze,
    write_allocation_research_evidence_freeze,
)


def main() -> None:
    payload = build_allocation_research_evidence_freeze()
    metadata = payload["metadata"]
    summary = payload["summary"]
    hypothesis_status = payload["hypothesis_status"]
    boundary = payload["decision_boundary_summary"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V9.9 Allocation Research Evidence Freeze & Decision Boundary Summary"
    assert summary["research_state"] == "frozen"
    assert summary["evidence_scope"] == "V9.1-V9.8"
    assert summary["hypothesis_count"] == 4
    assert summary["retained_research_direction_count"] == 2
    assert summary["paused_research_direction_count"] == 2
    assert summary["supported_research_only_count"] == 1
    assert summary["inconclusive_research_count"] == 1
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
    assert summary["conclusion"] == "allocation_research_evidence_frozen_no_strategy_no_allocation"

    assert hypothesis_status["H1"]["status"] == "freeze"
    assert hypothesis_status["H2"]["status"] == "inconclusive"
    assert hypothesis_status["H3"]["status"] == "freeze"
    assert hypothesis_status["H4"]["status"] == "supported_research_only"
    assert hypothesis_status["H2"]["decision_boundary"] == "retain_research_direction"
    assert hypothesis_status["H4"]["decision_boundary"] == "retain_research_direction"
    assert hypothesis_status["H1"]["decision_boundary"] == "pause_research_direction"
    assert hypothesis_status["H3"]["decision_boundary"] == "pause_research_direction"
    for row in hypothesis_status.values():
        assert row["allowed_next_step"] == "research_evidence_review_only"
        assert row["promotion_allowed"] is False
        assert row["strategy_promotion"] is False
        assert row["allocation_ready"] is False
        assert row["investable_output"] is False
        joined = " ".join(str(value) for value in row.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert set(boundary["retained_research_directions"]) == {"H2", "H4"}
    assert set(boundary["paused_research_directions"]) == {"H1", "H3"}
    assert "do_not_add_new_state_layer" in boundary["prohibited_next_actions"]
    assert "do_not_add_new_hypothesis" in boundary["prohibited_next_actions"]
    assert "do_not_add_new_explanation_layer" in boundary["prohibited_next_actions"]

    assert time_safety["uses_v9_1_to_v9_8_artifacts_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["no_result_based_parameter_change"] is True
    assert constraints["research_only"] is True
    assert constraints["evidence_freeze_only"] is True
    assert constraints["uses_v9_1_to_v9_8_artifacts_only"] is True
    assert constraints["does_not_add_state_layer"] is True
    assert constraints["does_not_add_hypothesis"] is True
    assert constraints["does_not_add_explanation_layer"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_allocation_research_evidence_freeze(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_allocation_research_evidence_freeze(
            payload,
            Path(tmpdir) / "allocation_research_evidence_freeze.json",
        )
        assert output.exists()

    print("test_allocation_research_evidence_freeze ok")


if __name__ == "__main__":
    main()
