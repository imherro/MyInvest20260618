from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from tenbagger.behavior import BehaviorFlowEngine
from tenbagger.regime import MarketRegimeEngine
from tenbagger.structure import MarketStructureEngine, StructureValidator


def _prices() -> pd.DataFrame:
    rows = []
    start = date(2023, 1, 2)
    for idx in range(6):
        close = 20 + idx
        for day in range(220):
            current = start + timedelta(days=day)
            if current.weekday() >= 5:
                continue
            drift = 0.001 + idx * 0.0001
            shock = -0.005 if day % 47 == 0 else 0.0
            close = close * (1 + drift + shock)
            rows.append(
                {
                    "ts_code": f"S{idx}",
                    "date": current.isoformat(),
                    "close": close,
                    "industry": "tech" if idx < 3 else "health",
                }
            )
    return pd.DataFrame(rows)


def _index_data(prices: pd.DataFrame) -> pd.DataFrame:
    market = prices.groupby("date", as_index=False)["close"].mean()
    return pd.concat(
        [
            market.assign(ts_code="000300.SH", index_name="CSI300", volume=100000, amount=500000),
            market.assign(ts_code="000905.SH", index_name="CSI500", volume=120000, amount=600000),
        ],
        ignore_index=True,
    )


def _behavior_daily(prices: pd.DataFrame) -> pd.DataFrame:
    regime = MarketRegimeEngine().run(_index_data(prices)).daily
    return BehaviorFlowEngine().run(regime).daily


def test_structure_engine_outputs_required_components() -> None:
    prices = _prices()
    result = MarketStructureEngine().run(prices, _behavior_daily(prices))
    latest = result.latest

    component_sum = (
        latest["trend_component"]
        + latest["flow_component"]
        + latest["volatility_component"]
        + latest["noise_component"]
    )
    assert abs(component_sum - 1.0) < 1e-6
    assert latest["correlation_regime"] in {"low", "medium", "high"}
    assert latest["structure_state"]
    assert 0 <= latest["structural_shock_probability"] <= 1


def test_structure_validator_keeps_observational_contract() -> None:
    prices = _prices()
    daily = MarketStructureEngine().run(prices, _behavior_daily(prices)).daily
    validation = StructureValidator().validate(daily)

    assert validation["uses_future_return_labels"] is False
    assert validation["uses_alpha_factors"] is False
    assert validation["purely_observational"] is True
    assert validation["components_sum_to_one"] is True
