from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_experiment_phase1_validation import (
    build_allocation_experiment_phase1_validation,
    validate_allocation_experiment_phase1_validation,
    write_allocation_experiment_phase1_validation,
)


def main() -> None:
    payload = build_allocation_experiment_phase1_validation()
    metadata = payload["metadata"]
    summary = payload["summary"]
    schema = payload["schema"]
    hashes = payload["freeze_hashes"]
    validation_results = payload["validation_results"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V9.6 Allocation Research Experiment Phase 1 Validation"
    assert summary["source_context"] == "risk_controlled_opportunity_watch"
    assert summary["validation_result_count"] == 4
    assert summary["supported_count"] == 2
    assert summary["inconclusive_count"] == 2
    assert summary["unsupported_count"] == 0
    assert summary["promotion_allowed"] is False
    assert summary["ready_for_asset_selection"] is False
    assert summary["ready_for_etf_mapping"] is False
    assert summary["ready_for_weight_generation"] is False
    assert summary["ready_for_optimization"] is False
    assert summary["ready_for_trade"] is False
    assert summary["promoted_to_candidate"] is False
    assert summary["investable_output_generated"] is False
    assert summary["conclusion"] == "allocation_experiment_phase1_validated_research_only_no_promotion"

    forbidden = set(schema["forbidden_outputs"])
    assert "asset_selection" in forbidden
    assert "etf_mapping" in forbidden
    assert "portfolio_weight" in forbidden
    assert "exposure_percent" in forbidden
    assert "optimization" in forbidden

    assert hashes
    for value in hashes.values():
        assert len(value) == 64

    result_by_id = {row["experiment_id"]: row for row in validation_results}
    assert result_by_id["H1"]["validation_status"] == "inconclusive"
    assert result_by_id["H2"]["validation_status"] == "supported"
    assert result_by_id["H3"]["validation_status"] == "inconclusive"
    assert result_by_id["H4"]["validation_status"] == "supported"
    for result in validation_results:
        assert result["promotion_allowed"] is False
        assert result["investable_output"] is False
        joined = " ".join(str(value) for value in result.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert time_safety["uses_frozen_artifacts_only"] is True
    assert time_safety["input_hashes_recorded"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["no_result_based_template_changes"] is True
    assert data_quality["no_asset_selection"] is True
    assert data_quality["no_etf_mapping"] is True
    assert data_quality["no_weight_generation"] is True
    assert data_quality["no_parameter_scan"] is True
    assert data_quality["no_optimization"] is True
    assert data_quality["phase1_outputs_research_only"] is True
    assert constraints["research_only"] is True
    assert constraints["phase1_validation_only"] is True
    assert constraints["uses_frozen_artifacts_only"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_exposure_percent"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["no_buy_sell_signal"] is True
    assert constraints["no_rebalance_instruction"] is True
    assert constraints["promotion_allowed_false"] is True
    assert audit["audit_status"] == "passed"
    assert validate_allocation_experiment_phase1_validation(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_allocation_experiment_phase1_validation(
            payload,
            Path(tmpdir) / "allocation_experiment_phase1_validation.json",
        )
        assert output.exists()

    print("test_allocation_experiment_phase1 ok")


if __name__ == "__main__":
    main()
