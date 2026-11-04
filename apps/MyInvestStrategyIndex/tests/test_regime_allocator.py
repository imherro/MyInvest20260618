from __future__ import annotations

import numpy as np
import pandas as pd

from myinvest_strategy_index.regime_allocator import (
    ASSET_CODES,
    BOND_CODE,
    EQUITY_CODE,
    FREE_CASH_FLOW_CODE,
    GOLD_CODE,
    get_dynamic_weights,
)


def test_get_dynamic_weights_maps_regime_rules() -> None:
    regime = pd.Series(
        [1, 0, -1],
        index=pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-31"]),
    )

    weights = get_dynamic_weights(regime)

    assert list(weights.columns) == list(ASSET_CODES)
    assert weights.loc["2024-01-31", EQUITY_CODE] == 0.50
    assert weights.loc["2024-01-31", FREE_CASH_FLOW_CODE] == 0.30
    assert weights.loc["2024-01-31", GOLD_CODE] == 0.10
    assert weights.loc["2024-01-31", BOND_CODE] == 0.10
    assert weights.loc["2024-02-29", EQUITY_CODE] == 0.15
    assert weights.loc["2024-02-29", FREE_CASH_FLOW_CODE] == 0.40
    assert weights.loc["2024-02-29", GOLD_CODE] == 0.20
    assert weights.loc["2024-02-29", BOND_CODE] == 0.25
    assert weights.loc["2024-03-31", EQUITY_CODE] == 0.05
    assert weights.loc["2024-03-31", FREE_CASH_FLOW_CODE] == 0.15
    assert weights.loc["2024-03-31", GOLD_CODE] == 0.35
    assert weights.loc["2024-03-31", BOND_CODE] == 0.45


def test_get_dynamic_weights_sums_to_one_and_has_no_nan() -> None:
    dates = pd.date_range("2024-01-01", periods=90, freq="D")
    regime = pd.Series(np.where(np.arange(len(dates)) % 3 == 0, 1, np.nan), index=dates)

    weights = get_dynamic_weights(regime)

    assert len(weights) == len(regime)
    assert not weights.isna().any().any()
    assert np.allclose(weights.sum(axis=1), 1.0)


def test_get_dynamic_weights_handles_invalid_regime_as_neutral() -> None:
    regime = pd.Series([2, -2, np.nan], index=pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-31"]))

    weights = get_dynamic_weights(regime)

    assert (weights[EQUITY_CODE] == 0.15).all()
    assert (weights[FREE_CASH_FLOW_CODE] == 0.40).all()
    assert (weights[GOLD_CODE] == 0.20).all()
    assert (weights[BOND_CODE] == 0.25).all()


def test_get_dynamic_weights_is_monthly_stable_between_rebalance_dates() -> None:
    dates = pd.date_range("2024-01-31", "2024-02-28", freq="D")
    alternating_regime = pd.Series(np.where(np.arange(len(dates)) % 2 == 0, 1, -1), index=dates)

    weights = get_dynamic_weights(alternating_regime)

    february_weights = weights.loc["2024-02-01":"2024-02-28"]
    assert len(february_weights.drop_duplicates()) == 1
    assert (february_weights[EQUITY_CODE] == 0.50).all()
