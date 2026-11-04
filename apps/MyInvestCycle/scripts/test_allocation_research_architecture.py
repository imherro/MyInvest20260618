from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_research_boundary import (
    build_allocation_research_architecture,
    validate_allocation_research_boundary,
    write_allocation_research_architecture,
)


def main() -> None:
    payload = build_allocation_research_architecture()
    metadata = payload["metadata"]
    summary = payload["summary"]
    schema = payload["schema"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V9.1 Allocation Research Architecture Foundation"
    assert summary["environment_context"] == "risk_controlled_opportunity_watch"
    assert summary["opportunity_state"] == "feature_attribution_not_ready_for_opportunity_score"
    assert summary["allocation_research_ready"] is False
    assert summary["ready_for_asset_selection"] is False
    assert summary["ready_for_etf_mapping"] is False
    assert summary["ready_for_weight_generation"] is False
    assert summary["ready_for_backtest"] is False
    assert summary["ready_for_trade"] is False
    assert summary["conclusion"] == "allocation_research_architecture_defined_not_ready"

    forbidden = set(schema["forbidden_outputs"])
    assert "portfolio_weight" in forbidden
    assert "asset_selection" in forbidden
    assert "etf_mapping" in forbidden
    assert "trade_signal" in forbidden
    assert "backtest_optimization" in forbidden

    assert time_safety["uses_frozen_v6_outputs_only"] is True
    assert time_safety["uses_frozen_v7_outputs_only"] is True
    assert time_safety["uses_frozen_v8_outputs_only"] is True
    assert time_safety["does_not_recompute_features"] is True
    assert time_safety["does_not_recompute_forward_returns"] is True
    assert data_quality["uses_frozen_v6_v7_v8_only"] is True
    assert data_quality["no_allocation_calculation"] is True
    assert data_quality["no_asset_selection"] is True
    assert data_quality["no_etf_mapping"] is True
    assert data_quality["no_weight_generation"] is True
    assert data_quality["no_backtest"] is True
    assert constraints["architecture_only"] is True
    assert constraints["research_only"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_select_assets"] is True
    assert constraints["does_not_map_etf"] is True
    assert constraints["does_not_run_backtest"] is True
    assert constraints["no_trade_signal"] is True
    assert audit["audit_status"] == "passed"
    assert validate_allocation_research_boundary(payload)["audit_status"] == "passed"

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_allocation_research_architecture(
            payload,
            Path(tmpdir) / "allocation_research_architecture.json",
        )
        assert output.exists()

    print("test_allocation_research_architecture ok")


if __name__ == "__main__":
    main()
