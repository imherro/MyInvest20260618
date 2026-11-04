from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from external_validation.research_phase_closure import (
    build_research_phase_closure,
    validate_research_phase_closure,
    write_research_phase_closure,
)


def main() -> None:
    payload = build_research_phase_closure()
    metadata = payload["metadata"]
    summary = payload["summary"]
    validated = payload["validated_for_observation_only"]
    not_verified = payload["not_verified_for_investment_use"]
    prohibitions = payload["permanent_prohibitions"]
    phase_evidence = payload["phase_evidence"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V11.4 Research Phase Closure & Final Architecture Freeze"
    assert len(metadata["input_hashes"]) == 5
    for value in metadata["input_hashes"].values():
        assert len(value) == 64
    assert summary["research_phase"] == "closed"
    assert summary["closure_status"] == "final_architecture_frozen"
    assert summary["risk_research_status"] == "validated_for_observation_only"
    assert summary["protection_research_status"] == "research_value_supported_observation_only"
    assert summary["contradiction_governance_status"] == "validated_for_research_governance_only"
    assert summary["opportunity_research_status"] == "not_ready"
    assert summary["allocation_status"] == "not_ready"
    assert summary["asset_selection_status"] == "disabled"
    assert summary["portfolio_construction_status"] == "not_ready"
    assert summary["trading_status"] == "disabled"
    assert summary["automatic_allocation_status"] == "disabled"
    assert summary["project_completion_status"] == "research_phase_closed_project_not_complete"
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
    assert summary["conclusion"] == "v6_to_v11_research_phase_closed_no_strategy_no_allocation"

    assert len(validated) == 3
    assert "opportunity_prediction" in not_verified
    assert "allocation_alpha" in not_verified
    assert "asset_selection" in not_verified
    assert "portfolio_construction" in not_verified
    assert "automatic_allocation" in prohibitions
    assert "automatic_trading" in prohibitions
    assert phase_evidence["v6"]["status"] == "frozen"
    assert phase_evidence["v7"]["status"] == "frozen"
    assert phase_evidence["v8"]["status"] == "frozen"
    assert phase_evidence["v9_v10"]["status"] == "frozen"
    assert phase_evidence["v11"]["status"] == "frozen"
    assert phase_evidence["v11"]["h2_status"] == "inconclusive"

    assert time_safety["uses_frozen_v6_to_v11_sources_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_market_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_add_research_layer"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["research_only"] is True
    assert constraints["phase_closure_only"] is True
    assert constraints["uses_frozen_v6_to_v11_sources_only"] is True
    assert constraints["does_not_add_research_layer"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True

    joined = " ".join(str(value) for value in payload.values())
    assert "510" not in joined
    assert "159" not in joined
    assert "%" not in joined
    assert audit["audit_status"] == "passed"
    assert validate_research_phase_closure(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_research_phase_closure(
            payload,
            Path(tmpdir) / "research_phase_closure.json",
        )
        assert output.exists()

    print("test_research_phase_closure ok")


if __name__ == "__main__":
    main()
