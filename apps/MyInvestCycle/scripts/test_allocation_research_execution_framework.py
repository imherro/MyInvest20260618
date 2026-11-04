from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_research_execution_framework import (
    build_allocation_research_execution_framework,
    validate_allocation_research_execution_framework,
    write_allocation_research_execution_framework,
)


def main() -> None:
    payload = build_allocation_research_execution_framework()
    metadata = payload["metadata"]
    summary = payload["summary"]
    runs = payload["execution_runs"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V10.1 Allocation Research Execution Framework"
    assert len(metadata["input_hashes"]) == 6
    for value in metadata["input_hashes"].values():
        assert len(value) == 64
    assert summary["execution_phase"] == "V10.1"
    assert summary["source_research_state"] == "frozen"
    assert summary["run_count"] == 2
    assert summary["completed_run_count"] == 2
    assert summary["supported_count"] == 1
    assert summary["inconclusive_count"] == 1
    assert summary["unsupported_count"] == 0
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
    assert summary["conclusion"] == "allocation_research_execution_records_completed_no_strategy_no_allocation"

    result_by_id = {row["experiment_id"]: row for row in runs}
    assert set(result_by_id) == {"H2", "H4"}
    assert result_by_id["H2"]["status"] == "completed"
    assert result_by_id["H2"]["result"] == "inconclusive"
    assert result_by_id["H2"]["source_hypothesis_status"] == "inconclusive"
    assert result_by_id["H4"]["status"] == "completed"
    assert result_by_id["H4"]["result"] == "supported"
    assert result_by_id["H4"]["source_hypothesis_status"] == "supported_research_only"
    for run in runs:
        assert run["run_id"].startswith(f"V10_1_{run['experiment_id']}_")
        assert len(run["input_hash"]) == 64
        assert run["research_only"] is True
        assert run["execution_scope"] == "frozen_evidence_replay"
        assert run["promotion_allowed"] is False
        assert run["strategy_promotion"] is False
        assert run["allocation_ready"] is False
        assert run["investable_output"] is False
        joined = " ".join(str(value) for value in run.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert time_safety["uses_frozen_v9_9_evidence_only"] is True
    assert time_safety["uses_frozen_v6_v7_v8_artifacts_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_market_backtest"] is True
    assert time_safety["no_result_based_parameter_change"] is True
    assert constraints["research_only"] is True
    assert constraints["execution_framework_only"] is True
    assert constraints["uses_frozen_v9_9_evidence_only"] is True
    assert constraints["uses_frozen_v6_v7_v8_artifacts_only"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert audit["audit_status"] == "passed"
    assert validate_allocation_research_execution_framework(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_allocation_research_execution_framework(
            payload,
            Path(tmpdir) / "allocation_research_execution_runs.json",
        )
        assert output.exists()

    print("test_allocation_research_execution_framework ok")


if __name__ == "__main__":
    main()
