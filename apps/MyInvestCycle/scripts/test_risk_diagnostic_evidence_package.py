from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.risk_diagnostic_evidence_package import (
    REQUIRED_EVIDENCE_IDS,
    build_risk_diagnostic_evidence_package,
    validate_risk_diagnostic_evidence_package,
    write_risk_diagnostic_evidence_package,
)


def main() -> None:
    payload = build_risk_diagnostic_evidence_package()
    metadata = payload["metadata"]
    package_metadata = payload["package_metadata"]
    summary = payload["summary"]
    evidence_items = payload["evidence_items"]
    lineage = payload["dataset_lineage"]
    validation_results = payload["validation_results"]
    cost_review = payload["cost_turnover_capacity_review"]
    shadow = payload["shadow_observation_log"]
    human = payload["human_review_record"]
    boundary = payload["boundary_violation_scan"]
    validator = payload["v13_2_validator_result"]
    audit_projection = payload["v12_3_audit_projection"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V14.1 Risk Diagnostic Layer Evidence Package Phase 0"
    assert package_metadata["package_id"] == "v14_1_risk_diagnostic_layer_phase0"
    assert package_metadata["component_id"] == "risk_diagnostic_layer"
    assert payload["component_id"] == "risk_diagnostic_layer"
    assert len(metadata["input_hashes"]) >= 10
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["evidence_status"] == "submitted"
    assert summary["package_status"] == "submitted_blocked_phase_0"
    assert summary["required_evidence_item_count"] == len(REQUIRED_EVIDENCE_IDS)
    assert summary["submitted_evidence_item_count"] == len(REQUIRED_EVIDENCE_IDS)
    assert summary["validation_result_count"] >= 5
    assert summary["implementation_gate_result"] == "blocked"
    assert summary["implementation_ready"] is False
    assert summary["manual_review_required"] is True
    assert summary["shadow_observation_required"] is True
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False
    assert summary["conclusion"] == "risk_diagnostic_evidence_submitted_blocked_no_strategy_no_allocation"

    evidence_ids = {item["evidence_id"] for item in evidence_items}
    assert evidence_ids == set(REQUIRED_EVIDENCE_IDS)
    statuses = {item["evidence_status"] for item in evidence_items}
    assert "submitted_negative" in statuses
    assert "submitted_inconclusive" in statuses
    assert "submitted_missing_required_live_log" in statuses

    assert lineage["lineage_status"] == "frozen_sources_hashed"
    assert lineage["source_count"] == len(lineage["source_files"])
    for source in lineage["source_files"]:
        assert len(source["hash"]) == 64
        assert source["path"].startswith("data/")

    for result in validation_results:
        assert result["window_id"]
        assert result["method"]
        assert result["pre_registered_metric"]
        assert result["result_status"]
        assert len(result["lineage_hash"]) == 64

    assert cost_review["review_status"] == "blocked_until_candidate_policy_exists"
    assert cost_review["cost_measured"] is False
    assert cost_review["turnover_measured"] is False
    assert cost_review["capacity_measured"] is False

    assert shadow["observation_status"] == "not_started_required_before_promotion"
    assert shadow["live_observation_count"] == 0
    assert shadow["shadow_trade_enabled"] is False
    assert shadow["required_before_promotion"] is True

    assert human["approval_status"] == "not_approved_for_implementation"
    assert human["stop_conditions_confirmed"] is True

    assert boundary["scan_status"] == "passed_no_investable_output"
    assert boundary["validator_package_status"] == "format_valid_not_ready_for_implementation"
    assert boundary["market_code_pattern_found"] is False
    assert boundary["boundary_violations"] == []
    assert boundary["forbidden_output_key_found"] is False

    assert validator["package_present"] is True
    assert validator["component_id"] == "risk_diagnostic_layer"
    assert validator["component_id_status"] == "valid"
    assert validator["package_status"] == "format_valid_not_ready_for_implementation"
    assert validator["validation_decision"] == "blocked_pending_manual_review_and_future_audit"
    assert validator["missing_items"] == []
    assert validator["boundary_violations"] == []
    assert validator["implementation_ready"] is False
    assert validator["market_code_pattern_found"] is False

    assert audit_projection["audit_status"] == "projected_blocked"
    assert audit_projection["audit_decision"] == "blocked_pending_shadow_and_manual_review"
    assert audit_projection["implementation_ready"] is False

    assert time_safety["uses_frozen_research_artifacts_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["single_component_evidence_package_only"] is True
    assert constraints["submits_real_research_evidence"] is True
    assert constraints["does_not_promote_component"] is True
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
    assert validate_risk_diagnostic_evidence_package(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_risk_diagnostic_evidence_package(
            payload,
            Path(tmpdir) / "risk_diagnostic_evidence_package.json",
        )
        assert output.exists()

    print("test_risk_diagnostic_evidence_package ok")


if __name__ == "__main__":
    main()
