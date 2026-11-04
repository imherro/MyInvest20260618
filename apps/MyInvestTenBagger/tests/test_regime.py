from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from tenbagger.regime import MarketRegimeEngine, RegimeValidator


def _index_data() -> pd.DataFrame:
    rows = []
    start = date(2023, 1, 2)
    for code in ["000300.SH", "000905.SH"]:
        close = 1000.0 if code == "000300.SH" else 900.0
        for day in range(220):
            current = start + timedelta(days=day)
            if current.weekday() >= 5:
                continue
            drift = 0.001 if day < 100 else -0.0005
            close = close * (1 + drift + (0.002 if code == "000905.SH" else 0.0))
            rows.append(
                {
                    "ts_code": code,
                    "date": current.isoformat(),
                    "close": close,
                    "volume": 100000 + day * 100,
                    "amount": 500000 + day * 1000,
                    "index_name": "CSI300" if code == "000300.SH" else "CSI500",
                }
            )
    return pd.DataFrame(rows)


def test_market_regime_engine_outputs_required_fields() -> None:
    result = MarketRegimeEngine().run(_index_data(), data_source={"source": "test"})

    latest = result.latest
    assert latest["trend_regime"] in {"bull", "bear", "sideways"}
    assert latest["volatility_regime"] in {"low", "medium", "high"}
    assert latest["liquidity_regime"] in {"expansion", "neutral", "contraction"}
    assert latest["behavior_state"] in {"risk_on", "risk_off", "panic", "euphoria", "transition"}
    assert 0 <= latest["regime_change_probability"] <= 1
    assert 0 <= latest["stability_score"] <= 1


def test_regime_validator_checks_continuity_without_future_labels() -> None:
    result = MarketRegimeEngine().run(_index_data())
    validation = RegimeValidator().validate(result.daily)

    assert validation["uses_future_return_labels"] is False
    assert validation["walk_forward_features_only"] is True
    assert "regime_autocorrelation" in validation
    assert "duration_distribution" in validation
