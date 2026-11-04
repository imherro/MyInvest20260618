from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.evidence_package_validator import (
    build_evidence_package_validation_engine,
    validate_evidence_package_validation_engine,
    validate_future_evidence_package,
    write_evidence_package_validation_engine,
)
from implementation_readiness.evidence_submission_protocol import (
    build_research_component_evidence_submission_protocol,
)


def main() -> None:
    payload = build_evidence_package_validation_engine()
    metadata = payload["metadata"]
    summary = payload["summary"]
    engine = payload["validation_engine"]
    current = payload["current_validation_result"]
    templates = payload["component_validation_templates"]
    source = payload["source_protocol_evidence"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V13.2 Evidence Package Validation Engine"
    assert len(metadata["input_hashes"]["research_component_evidence_submission_protocol"]) == 64

    assert summary["validation_engine_status"] == "defined"
    assert summary["current_package_status"] == "invalid_not_submitted"
    assert summary["current_package_present"] is False
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["component_template_count"] == 8
    assert summary["implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False
    assert summary["conclusion"] == "evidence_package_validation_engine_defined_no_strategy_no_allocation"

    assert engine["current_run_accepts_real_package"] is False
    assert engine["future_package_validation_supported"] is True
    assert engine["can_promote_component_without_manual_review"] is False
    assert "market_code_pattern_scan" in engine["supported_checks"]
    assert engine["market_code_detection"] == "generic_market_code_pattern_only_no_code_list_output"

    assert current["package_status"] == "invalid_not_submitted"
    assert current["package_present"] is False
    assert current["component_id_status"] == "not_checked"
    assert current["implementation_ready"] is False
    assert current["missing_items"]
    assert current["validation_decision"] == "blocked_no_package_submitted"

    assert len(templates) == 8
    for template in templates:
        assert template["package_status"] == "invalid_not_submitted"
        assert template["package_present"] is False
        assert template["schema_checked"] is False
        assert template["boundary_checked"] is False
        assert template["implementation_ready"] is False

    protocol = build_research_component_evidence_submission_protocol()
    synthetic_market_code = "510" + "300"
    bad_package = {
        "component_id": "risk_diagnostic_layer",
        "package_metadata": {"package_id": "demo"},
        "evidence_items": [],
        "dataset_lineage": {},
        "validation_results": [],
        "input_hashes": {},
        "note": f"hidden market code {synthetic_market_code} should be rejected in future package validation",
    }
    bad_result = validate_future_evidence_package(bad_package, protocol)
    assert bad_result["package_present"] is True
    assert bad_result["component_id_status"] == "valid"
    assert bad_result["implementation_ready"] is False
    assert "missing_required_field" in bad_result["boundary_violations"]
    assert "market_code_pattern_detected" in bad_result["boundary_violations"]

    assert source["v13_1_protocol_status"] == "defined"
    assert source["v13_1_submission_status"] == "not_submitted"
    assert source["v13_1_package_created"] is False
    assert source["v13_1_component_contract_count"] == 8

    assert time_safety["uses_v13_1_protocol_only"] is True
    assert time_safety["input_hash_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_compute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_accept_real_package_in_current_run"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["validation_engine_only"] is True
    assert constraints["current_run_no_real_package"] is True
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
    assert validate_evidence_package_validation_engine(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_evidence_package_validation_engine(
            payload,
            Path(tmpdir) / "evidence_package_validation_engine.json",
        )
        assert output.exists()

    print("test_evidence_package_validation_engine ok")


if __name__ == "__main__":
    main()
