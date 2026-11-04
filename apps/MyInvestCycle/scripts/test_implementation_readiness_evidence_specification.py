from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.evidence_specification import (
    build_implementation_readiness_evidence_specification,
    validate_implementation_readiness_evidence_specification,
    write_implementation_readiness_evidence_specification,
)


def main() -> None:
    payload = build_implementation_readiness_evidence_specification()
    metadata = payload["metadata"]
    summary = payload["summary"]
    schema = payload["readiness_schema"]
    components = payload["component_readiness_specifications"]
    gates = payload["global_readiness_gates"]
    shortcuts = payload["prohibited_shortcuts"]
    source = payload["source_boundary_evidence"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V12.2 Implementation Readiness Evidence Specification"
    assert len(metadata["input_hashes"]["research_to_implementation_boundary"]) == 64

    assert summary["readiness_specification_status"] == "defined"
    assert summary["implementation_readiness_status"] == "not_ready"
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["component_spec_count"] == 8
    assert summary["global_gate_count"] == 5
    assert summary["any_component_implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False
    assert summary["conclusion"] == "implementation_readiness_evidence_specification_defined_no_strategy_no_allocation"

    assert schema["current_specification_is_evaluation"] is False
    assert schema["current_specification_can_promote_component"] is False
    assert schema["all_requirements_must_be_future_verified"] is True
    assert schema["current_status_used_here"] == "not_evaluated"

    assert len(components) == 8
    components_by_id = {item["component_id"]: item for item in components}
    assert components_by_id["risk_diagnostic_layer"]["source_boundary_status"] == "observation_only"
    assert components_by_id["protection_research_value"]["source_boundary_status"] == "observation_only"
    assert components_by_id["contradiction_governance_layer"]["source_boundary_status"] == "research_governance_only"
    assert components_by_id["opportunity_prediction_layer"]["source_boundary_status"] == "isolated_not_ready"
    assert components_by_id["allocation_alpha_layer"]["source_boundary_status"] == "isolated_not_ready"
    assert components_by_id["asset_selection_layer"]["source_boundary_status"] == "disabled"
    assert components_by_id["portfolio_construction_layer"]["source_boundary_status"] == "not_ready"
    assert components_by_id["execution_layer"]["source_boundary_status"] == "disabled"
    for item in components:
        assert item["readiness_status"] == "not_ready_evidence_required"
        assert item["implementation_ready"] is False
        assert item["promotion_allowed"] is False
        assert item["evidence_current_status"] == "not_evaluated"
        assert item["required_evidence"]
        assert item["failure_conditions"]

    assert len(gates) == 5
    gate_ids = {item["gate_id"] for item in gates}
    assert "data_lineage_and_time_safety" in gate_ids
    assert "independent_out_of_sample_validation" in gate_ids
    assert "live_shadow_observation" in gate_ids
    for gate in gates:
        assert gate["required_before_implementation"] is True
        assert gate["current_status"] == "not_evaluated"

    assert "research_phase_closure_cannot_count_as_implementation_evidence" in shortcuts
    assert "observation_only_status_cannot_be_promoted_without_future_evidence" in shortcuts
    assert source["v12_1_boundary_status"] == "defined"
    assert source["v12_1_gate_result"] == "blocked"
    assert source["v12_1_component_count"] == 8

    assert time_safety["uses_v12_1_boundary_only"] is True
    assert time_safety["input_hash_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_compute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_evaluate_evidence"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["readiness_specification_only"] is True
    assert constraints["does_not_evaluate_evidence"] is True
    assert constraints["does_not_generate_strategy"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "510" + "880", "511" + "880", "159" + "915"):
        assert code not in joined
    assert "%" not in joined
    assert audit["audit_status"] == "passed"
    assert validate_implementation_readiness_evidence_specification(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_implementation_readiness_evidence_specification(
            payload,
            Path(tmpdir) / "implementation_readiness_evidence_specification.json",
        )
        assert output.exists()

    print("test_implementation_readiness_evidence_specification ok")


if __name__ == "__main__":
    main()
