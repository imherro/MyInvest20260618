from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_hypothesis_audit import (
    build_allocation_hypothesis_framework,
    validate_allocation_hypothesis_framework,
    write_allocation_hypothesis_framework,
)


def main() -> None:
    payload = build_allocation_hypothesis_framework()
    metadata = payload["metadata"]
    summary = payload["summary"]
    schema = payload["schema"]
    hypotheses = payload["hypotheses"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V9.2 Allocation Research Hypothesis Framework"
    assert summary["source_context"] == "risk_controlled_opportunity_watch"
    assert summary["hypothesis_count"] == 4
    assert summary["unvalidated_count"] == 4
    assert summary["validated_count"] == 0
    assert summary["hypothesis_framework_ready"] is False
    assert summary["ready_for_asset_selection"] is False
    assert summary["ready_for_etf_mapping"] is False
    assert summary["ready_for_weight_generation"] is False
    assert summary["ready_for_backtest"] is False
    assert summary["ready_for_optimization"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "allocation_hypothesis_framework_defined_unvalidated"

    forbidden = set(schema["forbidden_outputs"])
    assert "portfolio_weight" in forbidden
    assert "asset_selection" in forbidden
    assert "etf_mapping" in forbidden
    assert "exposure_percent" in forbidden
    assert "buy_signal" in forbidden
    assert "sell_signal" in forbidden
    assert "rebalance_instruction" in forbidden
    assert "backtest_result" in forbidden
    assert "optimization" in forbidden

    required_validation = set(schema["required_validation"])
    for hypothesis in hypotheses:
        assert hypothesis["status"] == "unvalidated"
        assert required_validation.issubset(set(hypothesis["required_validation"]))
        joined = " ".join(str(value) for value in hypothesis.values())
        assert "510" not in joined
        assert "159" not in joined
        assert "%" not in joined

    assert time_safety["uses_v9_1_artifact_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert time_safety["future_returns_not_used"] is True
    assert data_quality["no_asset_data_loaded"] is True
    assert data_quality["no_etf_data_loaded"] is True
    assert data_quality["no_backtest"] is True
    assert data_quality["no_parameter_scan"] is True
    assert data_quality["no_optimization"] is True
    assert data_quality["all_hypotheses_unvalidated"] is True
    assert constraints["research_only"] is True
    assert constraints["hypotheses_only"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_exposure_percent"] is True
    assert constraints["does_not_run_backtest"] is True
    assert constraints["does_not_optimize_parameters"] is True
    assert constraints["no_buy_sell_signal"] is True
    assert constraints["no_rebalance_instruction"] is True
    assert audit["audit_status"] == "passed"
    assert validate_allocation_hypothesis_framework(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_allocation_hypothesis_framework(
            payload,
            Path(tmpdir) / "allocation_research_hypotheses.json",
        )
        assert output.exists()

    print("test_allocation_hypothesis_audit ok")


if __name__ == "__main__":
    main()
