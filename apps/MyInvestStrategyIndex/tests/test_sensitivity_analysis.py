from __future__ import annotations

import math

import numpy as np
import pandas as pd

from myinvest_strategy_index.regime_allocator import BOND_CODE, EQUITY_CODE
from myinvest_strategy_index.sensitivity_analysis import (
    METRIC_COLUMNS,
    parameter_grid,
    run_sensitivity_analysis,
)


def _sample_prices(periods: int = 360) -> pd.DataFrame:
    dates = pd.date_range("2021-01-01", periods=periods, freq="B")
    steps = np.arange(periods)
    equity_returns = 0.00045 + 0.0035 * np.sin(steps / 21) + 0.0018 * np.cos(steps / 8)
    free_cash_flow_returns = 0.00035 + 0.0018 * np.sin(steps / 17)
    gold_returns = 0.00020 + 0.0012 * np.cos(steps / 13)
    bond_returns = 0.00012 + 0.0005 * np.sin(steps / 29)
    return pd.DataFrame(
        {
            EQUITY_CODE: 100 * np.cumprod(1.0 + equity_returns),
            "480092.CNI": 100 * np.cumprod(1.0 + free_cash_flow_returns),
            "518880.SH": 100 * np.cumprod(1.0 + gold_returns),
            BOND_CODE: 100 * np.cumprod(1.0 + bond_returns),
        },
        index=dates,
    )


def test_parameter_grid_contains_all_combinations() -> None:
    grid = parameter_grid(
        momentum_windows=[60, 90],
        volatility_windows=[10, 20],
        volatility_baseline_windows=[60],
        cost_bps_values=[0, 5],
    )

    assert len(grid) == 8
    assert (60, 10, 60, 0.0) in grid
    assert (90, 20, 60, 5.0) in grid


def test_run_sensitivity_analysis_outputs_matrix_and_heatmap_data() -> None:
    result = run_sensitivity_analysis(
        _sample_prices(),
        momentum_windows=[60, 90],
        volatility_windows=[10, 20],
        volatility_baseline_windows=[60],
        cost_bps_values=[0, 5],
    )

    matrix = result["sensitivity_matrix"]
    heatmap = result["heatmap_data"]
    stability = result["stability_metrics"]

    assert matrix.shape[0] == 8
    assert list(matrix.columns) == list(METRIC_COLUMNS)
    assert heatmap.shape[0] == 8
    assert {"mean_calmar", "std_calmar", "worst_calmar", "best_calmar"} == set(stability)
    assert not matrix.isna().any().any()
    assert not heatmap.isna().any().any()
    for value in stability.values():
        assert isinstance(value, float)
        assert math.isfinite(value)


def test_run_sensitivity_analysis_metrics_are_numeric_and_deterministic() -> None:
    kwargs = {
        "momentum_windows": [60],
        "volatility_windows": [10, 20],
        "volatility_baseline_windows": [60],
        "cost_bps_values": [0, 10],
    }
    first = run_sensitivity_analysis(_sample_prices(), **kwargs)
    second = run_sensitivity_analysis(_sample_prices(), **kwargs)

    first_matrix = first["sensitivity_matrix"]
    second_matrix = second["sensitivity_matrix"]
    assert np.isfinite(first_matrix.to_numpy()).all()
    pd.testing.assert_frame_equal(first_matrix, second_matrix)
    pd.testing.assert_frame_equal(first["heatmap_data"], second["heatmap_data"])
    assert first["stability_metrics"] == second["stability_metrics"]
