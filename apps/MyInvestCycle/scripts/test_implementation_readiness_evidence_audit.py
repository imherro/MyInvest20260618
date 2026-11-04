from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.evidence_audit import (
    build_implementation_readiness_evidence_audit,
    validate_implementation_readiness_evidence_audit,
    write_implementation_readiness_evidence_audit,
)


def main() -> None:
    payload = build_implementation_readiness_evidence_audit()
    metadata = payload["metadata"]
    summary = payload["summary"]
    schema = payload["audit_schema"]
    component_audits = payload["component_audits"]
    gate_audits = payload["global_gate_audits"]
    contract = payload["future_package_contract"]
    source = payload["source_specification_evidence"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V12.3 Implementation Readiness Evidence Audit Framework"
    assert len(metadata["input_hashes"]["implementation_readiness_evidence_specification"]) == 64

    assert summary["audit_framework_status"] == "defined"
    assert summary["evidence_package_status"] == "not_submitted"
    assert summary["evidence_evaluation_status"] == "not_started"
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["component_audit_count"] == 8
    assert summary["global_gate_audit_count"] == 5
    assert summary["submitted_component_count"] == 0
    assert summary["implementation_ready_component_count"] == 0
    assert summary["any_component_implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False
    assert summary["conclusion"] == "implementation_readiness_evidence_audit_framework_defined_no_strategy_no_allocation"

    assert schema["current_run_evaluates_submitted_evidence"] is False
    assert schema["future_framework_can_audit_submitted_package"] is True
    assert schema["audit_can_promote_component_without_manual_review"] is False
    assert "boundary_violation_scan" in schema["required_future_package_sections"]
    assert "forbidden_output_detected" in schema["automatic_rejection_conditions"]

    assert len(component_audits) == 8
    for item in component_audits:
        assert item["audit_status"] == "not_submitted"
        assert item["evidence_package_received"] is False
        assert item["evidence_items_received"] == []
        assert item["required_evidence_missing"]
        assert item["blocking_reasons"] == ["evidence_package_not_submitted"]
        assert item["boundary_violation_found"] is False
        assert item["implementation_ready"] is False
        assert item["promotion_allowed"] is False
        assert item["audit_decision"] == "blocked_until_future_evidence_package_submitted"

    assert len(gate_audits) == 5
    for item in gate_audits:
        assert item["audit_status"] == "not_submitted"
        assert item["required_before_implementation"] is True
        assert item["gate_passed"] is False
        assert item["missing_evidence"]

    assert contract["package_required"] is True
    assert contract["current_package_present"] is False
    assert contract["current_package_path"] is None
    assert contract["cannot_use_current_research_artifacts_as_substitute"] is True
    assert source["v12_2_readiness_specification_status"] == "defined"
    assert source["v12_2_gate_result"] == "blocked"
    assert source["v12_2_component_spec_count"] == 8

    assert time_safety["uses_v12_2_specification_only"] is True
    assert time_safety["input_hash_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_compute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_evaluate_strategy_return"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["audit_framework_only"] is True
    assert constraints["current_run_no_evidence_package"] is True
    assert constraints["does_not_evaluate_strategy_return"] is True
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
    assert validate_implementation_readiness_evidence_audit(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_implementation_readiness_evidence_audit(
            payload,
            Path(tmpdir) / "implementation_readiness_evidence_audit.json",
        )
        assert output.exists()

    print("test_implementation_readiness_evidence_audit ok")


if __name__ == "__main__":
    main()
