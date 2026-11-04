from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.evidence_submission_protocol import (
    build_research_component_evidence_submission_protocol,
    validate_research_component_evidence_submission_protocol,
    write_research_component_evidence_submission_protocol,
)


def main() -> None:
    payload = build_research_component_evidence_submission_protocol()
    metadata = payload["metadata"]
    summary = payload["summary"]
    schema = payload["submission_schema"]
    contracts = payload["component_submission_contracts"]
    rejection = payload["automatic_rejection_conditions"]
    state = payload["current_submission_state"]
    source = payload["source_audit_framework_evidence"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V13.1 Research Component Evidence Submission Protocol"
    assert len(metadata["input_hashes"]["implementation_readiness_evidence_audit"]) == 64

    assert summary["protocol_status"] == "defined"
    assert summary["submission_status"] == "not_submitted"
    assert summary["evidence_package_created"] is False
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["component_contract_count"] == 8
    assert summary["required_top_level_field_count"] == 10
    assert summary["implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False
    assert summary["conclusion"] == "research_component_evidence_submission_protocol_defined_no_strategy_no_allocation"

    assert schema["schema_version"] == "v13.1"
    assert schema["current_run_submits_evidence_package"] is False
    assert schema["future_package_required_for_audit"] is True
    assert schema["protocol_can_promote_component"] is False
    assert "package_metadata" in schema["required_top_level_fields"]
    assert "boundary_violation_scan" in schema["required_top_level_fields"]
    assert "stop_conditions_confirmed" in schema["manual_review_required_fields"]

    assert len(contracts) == 8
    for contract in contracts:
        assert contract["submission_scope"] == "future_evidence_package_only"
        assert contract["current_package_submitted"] is False
        assert contract["submission_allowed_now"] is False
        assert contract["required_evidence_items"]
        assert "component_id" in contract["required_package_sections"]
        assert "input_hashes" in contract["required_package_sections"]
        assert "broker_or_order_instruction" in contract["forbidden_package_content"]
        assert contract["initial_submission_status"] == "not_submitted"
        assert contract["promotion_allowed"] is False
        assert contract["implementation_ready"] is False

    assert "missing_required_top_level_field" in rejection
    assert "forbidden_package_content_detected" in rejection
    assert "broker_or_order_path_included" in rejection
    assert state["package_present"] is False
    assert state["package_path"] is None
    assert state["submitted_component_count"] == 0
    assert state["accepted_component_count"] == 0
    assert state["rejected_component_count"] == 0
    assert state["implementation_ready_component_count"] == 0
    assert source["v12_3_audit_framework_status"] == "defined"
    assert source["v12_3_evidence_package_status"] == "not_submitted"
    assert source["v12_3_ready_component_count"] == 0
    assert source["v12_3_gate_result"] == "blocked"

    assert time_safety["uses_v12_3_audit_framework_only"] is True
    assert time_safety["input_hash_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_compute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_submit_or_evaluate_evidence"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["submission_protocol_only"] is True
    assert constraints["current_run_no_submission"] is True
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
    assert validate_research_component_evidence_submission_protocol(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_research_component_evidence_submission_protocol(
            payload,
            Path(tmpdir) / "research_component_evidence_submission_protocol.json",
        )
        assert output.exists()

    print("test_research_component_evidence_submission_protocol ok")


if __name__ == "__main__":
    main()
