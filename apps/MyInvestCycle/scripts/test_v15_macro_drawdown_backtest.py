from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_macro_drawdown_backtest_result,
    validate_v15_macro_drawdown_backtest_result,
    write_v15_macro_drawdown_backtest_result,
)


REQUIRED_METRICS = {
    "total_return",
    "CAGR",
    "annual_return",
    "annual_alpha",
    "max_drawdown",
    "calmar",
    "sharpe",
    "yearly_returns",
    "regime_segment_returns",
    "drawdown_recovery_days",
}


def main() -> None:
    payload = build_v15_macro_drawdown_backtest_result()
    summary = payload["summary"]
    benchmarks = payload["benchmarks"]
    strategy = payload["strategy_results"]["macro_drawdown_strategy"]
    comparison = payload["comparison"]
    constraints = payload["constraints"]
    curve = payload["equity_curve"]

    assert payload["phase"] == "V15.3"
    assert payload["backtest_status"] == "completed"
    assert payload["research_backtest_only"] is True
    assert payload["not_production_signal"] is True
    assert payload["no_real_trade_order"] is True
    assert payload["strategy_scope"] == "macro_drawdown_regime_baseline"
    assert payload["input_materialization"] == "data/v15_backtest_dataset_materialization_status.json"
    assert payload["uses_point_in_time_inputs"] is True
    assert payload["uses_t_plus_one_execution"] is True

    assert summary["phase"] == "V15.3"
    assert summary["backtest_status"] == "completed"
    assert summary["strategy_scope"] == "macro_drawdown_regime_baseline"
    assert summary["research_backtest_only"] is True
    assert summary["not_production_signal"] is True
    assert summary["no_real_trade_order"] is True
    assert summary["sessions"] > 1000

    assert set(benchmarks) == {
        "cash_baseline",
        "csi_300_buy_hold",
        "csi_300_total_return_buy_hold",
        "shanghai_composite_buy_hold",
        "old_strategy_baseline",
    }
    rules = payload["strategy_rules"]
    assert summary["start_date"] >= "20160101"
    assert summary["return_index"] == "H00300.CSI"
    assert summary["transaction_cost_bps"] == 15
    assert rules["signal_index"] == "000300.SH"
    assert rules["return_index"] == "H00300.CSI"
    assert rules["drawdown_signal_uses_price_index"] is True
    assert rules["strategy_return_includes_dividend_reinvestment"] is True
    assert rules["transaction_cost_bps"] == 15
    assert REQUIRED_METRICS.issubset(strategy)
    assert isinstance(strategy["yearly_returns"], dict)
    assert isinstance(strategy["regime_segment_returns"], dict)
    assert strategy["CAGR"] is not None
    assert strategy["annual_return"] == strategy["CAGR"]
    assert strategy["annual_alpha"] is not None
    assert strategy["max_drawdown"] is not None
    assert strategy["calmar"] is not None
    assert strategy["sharpe"] is not None

    for key in ("cash_baseline", "csi_300_buy_hold", "shanghai_composite_buy_hold"):
        assert benchmarks[key]["CAGR"] is not None
        assert benchmarks[key]["max_drawdown"] is not None

    assert isinstance(comparison["beats_cash_baseline"], bool)
    assert isinstance(comparison["beats_csi_300_buy_hold"], bool)
    assert isinstance(comparison["improves_max_drawdown_vs_csi_300"], bool)
    assert isinstance(comparison["improves_calmar_vs_csi_300"], bool)
    assert comparison["result_must_not_be_marketed_as_success_without_beating_core_benchmarks"] is True

    assert constraints["no_broker_connection"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["not_intraday_signal"] is True
    assert constraints["not_production_trade_signal"] is True

    assert isinstance(curve, list)
    assert len(curve) == summary["sessions"]
    first = curve[0]
    last = curve[-1]
    for row in (first, last):
        assert "date" in row
        assert "phase" in row
        assert "drawdown" in row
        assert "target_exposure" in row
        assert "applied_exposure" in row
        assert "strategy_equity" in row
        assert "csi_300_equity" in row
        assert "csi_300_total_return_equity" in row
        assert row["transaction_cost_bps"] == 15
        assert "shanghai_composite_equity" in row
        assert "cash_equity" in row

    assert validate_v15_macro_drawdown_backtest_result(payload)["audit_status"] == "passed"

    for forbidden in ("trade_signal", "portfolio_weight", "broker_order", "real_order"):
        assert forbidden not in payload

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_v15_macro_drawdown_backtest_result(
            payload,
            Path(tmpdir) / "v15_macro_drawdown_backtest_result.json",
        )
        assert output.exists()

    print("test_v15_macro_drawdown_backtest ok")


if __name__ == "__main__":
    main()
