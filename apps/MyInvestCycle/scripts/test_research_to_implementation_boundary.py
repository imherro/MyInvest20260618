from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_boundary.research_to_implementation_boundary import (
    build_research_to_implementation_boundary,
    validate_research_to_implementation_boundary,
    write_research_to_implementation_boundary,
)


def main() -> None:
    payload = build_research_to_implementation_boundary()
    metadata = payload["metadata"]
    summary = payload["summary"]
    components = payload["component_boundaries"]
    gate = payload["implementation_entry_gate"]
    permitted = payload["permitted_current_outputs"]
    isolated = payload["explicitly_isolated_from_implementation"]
    evidence = payload["source_layer_evidence"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V12.1 Research-to-Implementation Boundary Design"
    assert len(metadata["input_hashes"]) == 3
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["boundary_status"] == "defined"
    assert summary["implementation_phase"] == "not_started"
    assert summary["research_phase_status"] == "closed"
    assert summary["implementation_candidate_count"] == 3
    assert summary["isolated_or_blocked_count"] == 5
    assert summary["global_implementation_allowed"] is False
    assert summary["investable_output"] is False
    assert summary["trade_ready"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["component_count"] == 8
    assert summary["conclusion"] == "research_to_implementation_boundary_defined_no_strategy_no_allocation"

    assert gate["current_gate_result"] == "blocked"
    assert gate["requires_new_evidence_before_any_implementation"] is True
    assert "independent_out_of_sample_validation" in gate["minimum_global_requirements"]
    assert "H2 external validation is inconclusive" in gate["blocked_reasons"]

    assert len(components) == 8
    components_by_id = {item["component_id"]: item for item in components}
    assert components_by_id["risk_diagnostic_layer"]["boundary_status"] == "observation_only"
    assert components_by_id["protection_research_value"]["boundary_status"] == "observation_only"
    assert components_by_id["contradiction_governance_layer"]["boundary_status"] == "research_governance_only"
    assert components_by_id["opportunity_prediction_layer"]["boundary_status"] == "isolated_not_ready"
    assert components_by_id["allocation_alpha_layer"]["boundary_status"] == "isolated_not_ready"
    assert components_by_id["asset_selection_layer"]["boundary_status"] == "disabled"
    assert components_by_id["portfolio_construction_layer"]["boundary_status"] == "not_ready"
    assert components_by_id["execution_layer"]["boundary_status"] == "disabled"
    for item in components:
        assert item["implementation_allowed"] is False
        assert item["required_before_implementation"]
        assert "manual_review_before_any_investable_use" in item["required_before_implementation"]

    assert "read_only_dashboard" in permitted
    assert "manual_research_review_context" in permitted
    assert "opportunity_prediction" in isolated
    assert "automatic_allocation" in isolated
    assert evidence["research_phase_closure"]["research_phase"] == "closed"
    assert evidence["research_phase_closure"]["investable_output"] is False
    assert evidence["v11_h2_freeze"]["h2_status"] == "inconclusive"

    assert time_safety["uses_frozen_boundary_inputs_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_recompute_market_data"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_change_prior_research_conclusions"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["boundary_design_only"] is True
    assert constraints["does_not_generate_strategy"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert constraints["requires_future_v12_evidence_before_implementation"] is True

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "510" + "880", "511" + "880", "159" + "915"):
        assert code not in joined
    assert "%" not in joined
    assert audit["audit_status"] == "passed"
    assert validate_research_to_implementation_boundary(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_research_to_implementation_boundary(
            payload,
            Path(tmpdir) / "research_to_implementation_boundary.json",
        )
        assert output.exists()

    print("test_research_to_implementation_boundary ok")


if __name__ == "__main__":
    main()
