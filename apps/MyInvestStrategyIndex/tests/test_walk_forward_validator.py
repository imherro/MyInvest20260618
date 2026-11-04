from __future__ import annotations

import math

import numpy as np
import pandas as pd

from myinvest_strategy_index.regime_allocator import BOND_CODE, EQUITY_CODE
from myinvest_strategy_index.walk_forward_validator import (
    STRATEGY_NAMES,
    run_walk_forward_backtest,
    walk_forward_split,
)


def _sample_prices(periods: int = 720) -> pd.DataFrame:
    dates = pd.date_range("2019-01-01", periods=periods, freq="B")
    steps = np.arange(periods)
    equity_returns = 0.00035 + 0.0040 * np.sin(steps / 31) + 0.0025 * np.sin(steps / 7)
    free_cash_flow_returns = 0.00042 + 0.0020 * np.sin(steps / 23)
    gold_returns = 0.00022 + 0.0016 * np.cos(steps / 19)
    bond_returns = 0.00016 + 0.0007 * np.sin(steps / 41)
    return pd.DataFrame(
        {
            EQUITY_CODE: 100 * np.cumprod(1.0 + equity_returns),
            "480092.CNI": 100 * np.cumprod(1.0 + free_cash_flow_returns),
            "518880.SH": 100 * np.cumprod(1.0 + gold_returns),
            BOND_CODE: 100 * np.cumprod(1.0 + bond_returns),
        },
        index=dates,
    )


def _optimizer_kwargs() -> dict[str, object]:
    return {
        "random_candidates": 400,
        "local_rounds": 1,
        "local_candidates": 120,
        "batch_size": 120,
    }


def test_walk_forward_split_has_no_train_test_overlap() -> None:
    windows = walk_forward_split(
        _sample_prices(),
        train_years=1,
        test_months=3,
        step_months=3,
        min_train_rows=200,
        min_test_rows=40,
    )

    assert windows
    for window in windows:
        assert window.train_end < window.test_start
        assert window.train_prices.index.intersection(window.test_prices.index).empty


def test_run_walk_forward_backtest_outputs_window_and_aggregate_metrics() -> None:
    result = run_walk_forward_backtest(
        _sample_prices(),
        train_years=1,
        test_months=3,
        step_months=3,
        static_optimizer_kwargs=_optimizer_kwargs(),
    )

    assert result["window_metrics"]
    assert set(result["mean_metrics"]) == set(STRATEGY_NAMES)
    assert set(result["std_metrics"]) == set(STRATEGY_NAMES)
    assert set(result["worst_case_metrics"]) == set(STRATEGY_NAMES)

    for window in result["window_metrics"]:
        assert set(window["metrics"]) == set(STRATEGY_NAMES)
        for metrics in window["metrics"].values():
            for value in metrics.values():
                assert isinstance(value, float)
                assert not math.isnan(value)

    equity = result["aggregated_equity_curve"]
    returns = result["aggregated_returns"]
    assert list(equity.columns) == list(STRATEGY_NAMES)
    assert equity.index.equals(returns.index)


def test_run_walk_forward_backtest_is_stable_across_runs() -> None:
    kwargs = {
        "train_years": 1,
        "test_months": 3,
        "step_months": 3,
        "seed": 11,
        "static_optimizer_kwargs": _optimizer_kwargs(),
    }
    first = run_walk_forward_backtest(_sample_prices(), **kwargs)
    second = run_walk_forward_backtest(_sample_prices(), **kwargs)

    assert first["mean_metrics"] == second["mean_metrics"]
    assert first["std_metrics"] == second["std_metrics"]
    assert first["worst_case_metrics"] == second["worst_case_metrics"]
    pd.testing.assert_frame_equal(first["aggregated_equity_curve"], second["aggregated_equity_curve"])
