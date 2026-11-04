from __future__ import annotations

import numpy as np
import pandas as pd

from myinvest_strategy_index.regime_detector import (
    DEFAULT_BOND_CODE,
    DEFAULT_EQUITY_CODE,
    detect_regime,
)


def _sample_prices(periods: int = 320) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=periods, freq="B")
    steps = np.arange(periods)
    equity_returns = 0.0004 + 0.0020 * np.sin(steps / 17)
    bond_returns = 0.0001 + 0.0005 * np.cos(steps / 29)
    gold_returns = 0.0002 + 0.0010 * np.sin(steps / 23)
    return pd.DataFrame(
        {
            DEFAULT_EQUITY_CODE: 100 * np.cumprod(1.0 + equity_returns),
            DEFAULT_BOND_CODE: 100 * np.cumprod(1.0 + bond_returns),
            "518880.SH": 100 * np.cumprod(1.0 + gold_returns),
        },
        index=dates,
    )


def test_detect_regime_returns_aligned_non_nan_series() -> None:
    prices = _sample_prices()

    regime = detect_regime(prices)

    assert len(regime) == len(prices)
    assert regime.index.equals(prices.index)
    assert regime.name == "regime"
    assert not regime.isna().any()


def test_detect_regime_values_are_limited_to_three_states() -> None:
    regime = detect_regime(_sample_prices())

    assert set(regime.unique()).issubset({-1, 0, 1})


def test_detect_regime_does_not_use_same_day_close() -> None:
    prices = _sample_prices()
    changed = prices.copy()
    changed.iloc[-1, changed.columns.get_loc(DEFAULT_EQUITY_CODE)] *= 3.0

    original_regime = detect_regime(prices)
    changed_regime = detect_regime(changed)

    pd.testing.assert_series_equal(original_regime, changed_regime)
