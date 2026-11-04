from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_backtest_dataset_manifest,
    validate_v15_backtest_dataset_manifest,
    write_v15_backtest_dataset_manifest,
)


def main() -> None:
    payload = build_v15_backtest_dataset_manifest()
    summary = payload["summary"]
    groups = payload["dataset_groups"]
    targets = payload["future_backtest_targets"]
    quality = payload["data_quality_requirements"]
    constraints = payload["constraints"]

    assert payload["phase"] == "V15.1"
    assert payload["dataset_status"] == "manifest_ready"
    assert payload["does_not_run_strategy"] is True
    assert payload["does_not_generate_position"] is True
    assert payload["does_not_generate_trade_signal"] is True
    assert payload["no_backtest_result"] is True
    assert payload["production_trade_enabled"] is False
    assert summary["phase"] == "V15.1"
    assert summary["dataset_status"] == "manifest_ready"
    assert summary["no_backtest_result"] is True
    assert summary["production_trade_enabled"] is False
    assert summary["broker_connection_enabled"] is False
    assert summary["real_order_generation_enabled"] is False

    assert set(groups) == {"broad_indices", "sector_indices", "macro_cycle", "drawdown_context", "structural_bull"}
    for group in groups.values():
        assert group["dataset_group_status"] == "manifest_defined"
        assert group["fields"]

    assert targets["macro_drawdown_strategy"] is True
    assert targets["structural_bull_rotation_strategy"] is True
    assert targets["old_strategy_baseline"] is True
    assert quality["point_in_time_required"] is True
    assert quality["release_date_safe_required"] is True
    assert constraints["dataset_builder_only"] is True
    assert constraints["does_not_fetch_full_dataset"] is True
    assert constraints["does_not_run_strategy"] is True
    assert constraints["no_backtest_result"] is True
    assert constraints["does_not_generate_position"] is True
    assert constraints["does_not_generate_fund_mapping"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["no_allocation"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["no_trade"] is True
    assert constraints["no_broker_connection"] is True
    assert constraints["production_trade_enabled"] is False
    assert validate_v15_backtest_dataset_manifest(payload)["audit_status"] == "passed"

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "159" + "915"):
        assert code not in joined

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_v15_backtest_dataset_manifest(payload, Path(tmpdir) / "v15_backtest_dataset_manifest.json")
        assert output.exists()

    print("test_v15_backtest_dataset_builder ok")


if __name__ == "__main__":
    main()
