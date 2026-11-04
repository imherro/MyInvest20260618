from __future__ import annotations

import json

import pytest

from myinvest_strategy_index.config import load_settings
from myinvest_strategy_index.cycle_backtests import (
    get_cycle_backtest_detail,
    get_cycle_backtest_index,
)


def _write_backtest(path, *, strategy_id: str, total_return: float, max_drawdown: float, sessions: int = 252) -> None:
    payload = {
        "metadata": {
            "engine": f"{strategy_id} Backtest",
            "strategy_id": strategy_id,
            "description": "sample strategy",
            "method": ["sample method"],
            "evaluation_only": True,
            "no_trade_execution": True,
        },
        "summary": {
            "strategy_id": strategy_id,
            "strategy_name": f"{strategy_id} strategy",
            "short_name": strategy_id,
            "start_date": "20200102",
            "end_date": "20210104",
            "sessions": sessions,
            "rebalance_count": 3,
            "strategy_total_return": total_return,
            "max_drawdown": max_drawdown,
            "sharpe": 1.2,
            "alpha_vs_equal_weight": 0.12,
            "average_turnover": 0.05,
            "latest_signal": "sample_signal",
            "latest_signal_date": "20210104",
            "latest_weights": {"510300.SH": 0.6, "511880.SH": 0.4},
            "comparison_assets": [{"code": "equal_weight", "total_return": 0.1}],
        },
        "equity_curve": [
            {"date": "20200102", "strategy_equity": 1.0, "equal_weight_equity": 1.0},
            {"date": "20210104", "strategy_equity": 1.2, "equal_weight_equity": 1.1},
        ],
        "signals": [{"date": "20210104", "target_weights": {"510300.SH": 0.6}}],
        "validation": {"no_lookahead_bias": True},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_cycle_backtest_index_standardizes_json_results(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    backtest_dir = tmp_path / "cycle" / "strategy_backtests"
    backtest_dir.mkdir(parents=True)
    _write_backtest(backtest_dir / "four-asset.json", strategy_id="four-asset", total_return=0.2, max_drawdown=-0.1)
    _write_backtest(
        backtest_dir / "free-cash-flow-chinext-dynamic.json",
        strategy_id="free-cash-flow-chinext-dynamic",
        total_return=0.3,
        max_drawdown=-0.2,
    )

    payload = get_cycle_backtest_index(settings, backtest_dir=backtest_dir)

    assert payload["ok"] is True
    assert payload["count"] == 2
    assert not payload["errors"]
    strategies = {item["strategy_id"]: item for item in payload["strategies"]}
    assert strategies["four-asset"]["category"] == "资产配置"
    assert strategies["four-asset"]["annualized_return"] == pytest.approx(0.2)
    assert strategies["four-asset"]["calmar"] == pytest.approx(2.0)
    assert strategies["free-cash-flow-chinext-dynamic"]["category"] == "自由现金流"


def test_cycle_backtest_detail_returns_curves_signals_and_comparison_assets(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    backtest_dir = tmp_path / "cycle" / "strategy_backtests"
    backtest_dir.mkdir(parents=True)
    _write_backtest(backtest_dir / "four-asset.json", strategy_id="four-asset", total_return=0.2, max_drawdown=-0.1)

    payload = get_cycle_backtest_detail(settings, "four-asset", backtest_dir=backtest_dir)

    assert payload["ok"] is True
    assert payload["summary"]["strategy_id"] == "four-asset"
    assert len(payload["equity_curve"]) == 2
    assert len(payload["signals"]) == 1
    assert payload["comparison_assets"][0]["code"] == "equal_weight"


def test_cycle_backtest_detail_rejects_invalid_strategy_id(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")

    with pytest.raises(ValueError):
        get_cycle_backtest_detail(settings, "../secret", backtest_dir=tmp_path)
