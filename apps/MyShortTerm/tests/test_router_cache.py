import pandas as pd

from shortterm_trader.data.router import _repair_cached_amount_units


def test_repair_cached_tushare_amount_units() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "date": pd.to_datetime(["2026-01-02"]),
            "open": [10.0],
            "high": [10.5],
            "low": [9.9],
            "close": [10.0],
            "volume": [1_000_000.0],
            "amount": [10_000.0],
            "source": ["tushare"],
        }
    )
    fixed = _repair_cached_amount_units(frame)
    assert fixed.iloc[0]["amount"] == 10_000_000.0

