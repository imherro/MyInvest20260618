from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.research_candidate_promotion_gate import (
    build_research_candidate_promotion_gate,
    validate_research_candidate_promotion_gate,
    write_research_candidate_promotion_gate,
)


def main() -> None:
    payload = build_research_candidate_promotion_gate()
    metadata = payload["metadata"]
    summary = payload["summary"]
    gate_results = payload["gate_results"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V9.7 Research Candidate Promotion Gate Audit"
    assert summary["gate_count"] == 4
    assert summary["continue_research_count"] == 2
    assert summary["freeze_count"] == 2
    assert summary["reject_for_now_count"] == 0
    assert summary["promotion_allowed"] is False
    assert summary["strategy_promotion"] is False
    assert summary["allocation_promotion"] is False
    assert summary["investable_output_generated"] is False
    assert summary["investable_output"] is False
    assert summary["ready_for_asset_selection"] is False
    assert summary["ready_for_etf_mapping"] is False
    assert summary["ready_for_weight_generation"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "research_candidate_gate_completed_no_strategy_promotion"

    result_by_id = {row["hypothesis_id"]: row for row in gate_results}
    assert result_by_id["H1"]["research_status"] == "freeze"
    assert result_by_id["H2"]["research_status"] == "continue_research"
    assert result_by_id["H3"]["research_status"] == "freeze"
    assert result_by_id["H4"]["research_status"] == "continue_research"

    for result in gate_results:
        assert result["research_status"] in {"continue_research", "freeze", "reject_for_now"}
        assert result["promotion_allowed"] is False
        assert result["promotion_to_strategy"] is False
        assert result["promotion_to_allocation"] is False
        assert result["investable_output"] is False
        joined = " ".join(str(value) for value in result.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert constraints["research_only"] is True
    assert constraints["gate_audit_only"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_research_candidate_promotion_gate(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_research_candidate_promotion_gate(
            payload,
            Path(tmpdir) / "research_candidate_promotion_gate.json",
        )
        assert output.exists()

    print("test_research_candidate_promotion_gate ok")


if __name__ == "__main__":
    main()
