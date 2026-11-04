from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.governance_freeze import (
    build_implementation_readiness_governance_freeze,
    validate_implementation_readiness_governance_freeze,
    write_implementation_readiness_governance_freeze,
)


def main() -> None:
    payload = build_implementation_readiness_governance_freeze()
    metadata = payload["metadata"]
    summary = payload["summary"]
    chain = payload["frozen_governance_chain"]
    boundaries = payload["implementation_boundaries"]
    not_completed = payload["not_completed"]
    next_phase = payload["recommended_next_phase"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V13.4 Implementation Readiness Governance Freeze"
    assert len(metadata["input_hashes"]) == 7
    for value in metadata["input_hashes"].values():
        assert len(value) == 64

    assert summary["governance_freeze_status"] == "frozen"
    assert summary["governance_chain_complete"] is True
    assert summary["frozen_stage_count"] == 6
    assert summary["implementation_candidate_status"] == "none_submitted"
    assert summary["future_evidence_submission_supported"] is True
    assert summary["implementation_ready"] is False
    assert summary["investable_output"] is False
    assert summary["strategy_output_generated"] is False
    assert summary["allocation_output_generated"] is False
    assert summary["trade_ready"] is False
    assert summary["project_completion_status"] == "governance_frozen_project_not_complete"
    assert summary["conclusion"] == "implementation_readiness_governance_frozen_no_strategy_no_allocation"

    assert len(chain) == 6
    versions = {item["version"] for item in chain}
    assert {"V12.1", "V12.2", "V12.3", "V13.1", "V13.2", "V13.3"} == versions
    for stage in chain:
        assert stage["status"] == "frozen"
        assert stage["implementation_ready"] is False

    assert boundaries["no_real_evidence_package_submitted"] is True
    assert boundaries["no_component_promoted"] is True
    assert boundaries["no_strategy_generated"] is True
    assert boundaries["no_allocation_generated"] is True
    assert boundaries["no_trade_path_enabled"] is True
    assert boundaries["future_work_must_choose_single_component"] is True
    assert boundaries["future_package_must_use_v13_1_protocol"] is True
    assert boundaries["future_package_must_pass_v13_2_validator"] is True
    assert boundaries["future_package_must_pass_v12_3_audit"] is True

    assert "real_component_evidence_submission" in not_completed
    assert "portfolio_construction" in not_completed
    assert next_phase["phase"] == "future_single_component_evidence_submission"
    assert next_phase["automatic_implementation_allowed"] is False
    assert len(next_phase["allowed_initial_components"]) == 8

    assert time_safety["uses_frozen_v12_to_v13_sources_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_read_market_price_data"] is True
    assert time_safety["does_not_compute_forward_returns"] is True
    assert time_safety["does_not_run_backtest"] is True
    assert time_safety["does_not_optimize_parameters"] is True
    assert time_safety["does_not_submit_or_evaluate_real_evidence"] is True
    assert time_safety["no_result_based_parameter_change"] is True

    assert constraints["governance_freeze_only"] is True
    assert constraints["does_not_submit_real_evidence"] is True
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
    assert validate_implementation_readiness_governance_freeze(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_implementation_readiness_governance_freeze(
            payload,
            Path(tmpdir) / "implementation_readiness_governance_freeze.json",
        )
        assert output.exists()

    print("test_implementation_readiness_governance_freeze ok")


if __name__ == "__main__":
    main()
