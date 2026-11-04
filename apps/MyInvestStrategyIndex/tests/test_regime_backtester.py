from __future__ import annotations

import math

import numpy as np
import pandas as pd

from myinvest_strategy_index.regime_allocator import ASSET_CODES, BOND_CODE, EQUITY_CODE
from myinvest_strategy_index.regime_backtester import (
    build_portfolio_returns,
    run_backtest_comparison,
)


def _sample_prices(periods: int = 520) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=periods, freq="B")
    steps = np.arange(periods)
    equity_returns = np.r_[
        np.full(170, 0.0010),
        -0.0012 + 0.0100 * np.sin(np.arange(170) / 2),
        np.full(periods - 340, 0.0008),
    ]
    free_cash_flow_returns = 0.00045 + 0.0018 * np.sin(steps / 19)
    gold_returns = 0.00025 + 0.0014 * np.cos(steps / 23)
    bond_returns = 0.00018 + 0.0006 * np.sin(steps / 31)
    return pd.DataFrame(
        {
            EQUITY_CODE: 100 * np.cumprod(1.0 + equity_returns),
            "480092.CNI": 100 * np.cumprod(1.0 + free_cash_flow_returns),
            "518880.SH": 100 * np.cumprod(1.0 + gold_returns),
            BOND_CODE: 100 * np.cumprod(1.0 + bond_returns),
        },
        index=dates,
    )


def test_build_portfolio_returns_uses_prior_weights() -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    prices = pd.DataFrame(
        {
            EQUITY_CODE: [100.0, 200.0, 200.0],
            "480092.CNI": [100.0, 100.0, 100.0],
            "518880.SH": [100.0, 100.0, 100.0],
            BOND_CODE: [100.0, 100.0, 200.0],
        },
        index=dates,
    )
    weights = pd.DataFrame(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        index=dates,
        columns=ASSET_CODES,
    )

    returns = build_portfolio_returns(prices, weights)

    assert returns.iloc[0] == 1.0
    assert returns.iloc[1] == 1.0


def test_run_backtest_comparison_outputs_metrics_and_aligned_curves() -> None:
    result = run_backtest_comparison(
        _sample_prices(),
        cost_bps=5.0,
        static_optimizer_kwargs={
            "random_candidates": 800,
            "local_rounds": 1,
            "local_candidates": 200,
            "batch_size": 200,
        },
    )

    assert set(result["metrics"]) == {"equal_weight", "static_calmar", "regime_switching"}
    required_metrics = {
        "cagr",
        "annualized_volatility",
        "sharpe_ratio",
        "max_drawdown",
        "calmar_ratio",
        "turnover",
    }
    for metrics in result["metrics"].values():
        assert set(metrics) == required_metrics
        for value in metrics.values():
            assert isinstance(value, float)
            assert math.isfinite(value)

    equity = result["equity_curves"]
    drawdown = result["drawdown_curves"]
    returns = result["returns"]
    assert list(equity.columns) == ["equal_weight", "static_calmar", "regime_switching"]
    assert equity.index.equals(drawdown.index)
    assert equity.index.equals(returns.index)


def test_run_backtest_comparison_regime_strategy_has_turnover() -> None:
    result = run_backtest_comparison(
        _sample_prices(),
        cost_bps=5.0,
        static_optimizer_kwargs={
            "random_candidates": 600,
            "local_rounds": 1,
            "local_candidates": 200,
            "batch_size": 200,
        },
    )

    assert result["metrics"]["regime_switching"]["turnover"] > 0
