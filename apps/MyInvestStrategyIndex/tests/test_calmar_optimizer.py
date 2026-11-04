from __future__ import annotations

import numpy as np
import pandas as pd

from myinvest_strategy_index.calmar_optimizer import (
    _project_to_capped_simplex,
    daily_returns,
    evaluate_portfolio,
    optimize_calmar,
)


def test_project_to_capped_simplex_respects_constraints() -> None:
    weights = _project_to_capped_simplex(np.array([2.0, 1.0, 0.5, -1.0]), 0.4)

    assert np.isclose(weights.sum(), 1.0)
    assert np.all(weights >= 0)
    assert np.all(weights <= 0.4 + 1e-12)


def test_optimize_calmar_beats_equal_weight_on_simple_sample() -> None:
    dates = pd.date_range("2020-01-01", periods=260, freq="B")
    steps = np.arange(len(dates))
    returns_data = {
        "a": 0.0009 + 0.0040 * np.sin(steps / 13),
        "b": 0.0003 + 0.0015 * np.sin(steps / 19),
        "c": -0.0001 + 0.0090 * np.sin(steps / 7),
        "d": -0.0002 + 0.0110 * np.cos(steps / 5),
    }
    prices = pd.DataFrame(
        {code: 100 * np.cumprod(1.0 + values) for code, values in returns_data.items()},
        index=dates,
    )
    returns = daily_returns(prices)

    result = optimize_calmar(
        returns,
        seed=7,
        random_candidates=1_000,
        local_rounds=2,
        local_candidates=400,
        batch_size=200,
    )
    equal_metrics = evaluate_portfolio(returns, np.full(4, 0.25))

    assert np.isclose(result.weights.sum(), 1.0)
    assert np.all(result.weights >= 0)
    assert np.all(result.weights <= 0.4 + 1e-12)
    assert result.metrics.calmar >= equal_metrics.calmar
