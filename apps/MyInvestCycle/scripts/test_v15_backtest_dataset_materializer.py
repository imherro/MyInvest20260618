from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_backtest_dataset_materialization_status,
    validate_v15_backtest_dataset_materialization_status,
    write_v15_backtest_dataset_materialization_status,
)


def main() -> None:
    payload = build_v15_backtest_dataset_materialization_status()
    summary = payload["summary"]
    coverage = payload["coverage"]
    quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert payload["phase"] == "V15.2"
    assert payload["materialization_status"] == "coverage_report_ready"
    assert payload["source_manifest"] == "data/v15_backtest_dataset_manifest.json"
    assert payload["dataset_groups_checked"] == 5
    assert payload["full_dataset_fetched"] is False
    assert payload["strategy_run"] is False
    assert payload["backtest_result_generated"] is False
    assert payload["position_generated"] is False
    assert payload["trade_signal_generated"] is False
    assert payload["production_trade_enabled"] is False

    assert summary["phase"] == "V15.2"
    assert summary["materialization_status"] == "coverage_report_ready"
    assert summary["full_dataset_fetched"] is False
    assert summary["strategy_run"] is False
    assert summary["backtest_result_generated"] is False
    assert summary["position_generated"] is False
    assert summary["trade_signal_generated"] is False
    assert summary["production_trade_enabled"] is False
    assert summary["source_count"] >= summary["available_source_count"] >= 1

    assert set(coverage) == {"broad_indices", "sector_indices", "macro_cycle", "drawdown_context", "structural_bull"}
    for group in coverage.values():
        assert group["dataset_group_status"] == "local_coverage_reported"
        assert group["required_source_count"] > 0
        assert group["manifest_field_count"] > 0
        assert group["missing_field_report"]["status"] == "defined"

    assert quality["point_in_time_check_defined"] is True
    assert quality["release_date_alignment_defined"] is True
    assert quality["survivorship_bias_check_defined"] is True
    assert quality["missing_field_report_defined"] is True
    assert quality["source_hash_recorded"] is True
    assert quality["no_live_fetch_attempted"] is True

    assert constraints["dataset_materialization_only"] is True
    assert constraints["does_not_run_strategy"] is True
    assert constraints["does_not_generate_position"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["no_broker_connection"] is True
    assert constraints["production_trade_enabled"] is False
    assert validate_v15_backtest_dataset_materialization_status(payload)["audit_status"] == "passed"

    for key in ("trade_signal", "portfolio_weight", "broker_order", "etf_mapping"):
        assert key not in payload

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_v15_backtest_dataset_materialization_status(
            payload,
            Path(tmpdir) / "v15_backtest_dataset_materialization_status.json",
        )
        assert output.exists()

    print("test_v15_backtest_dataset_materializer ok")


if __name__ == "__main__":
    main()
