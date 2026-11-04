import pandas as pd

from shortterm_trader.strategy.short_term import build_signal_frame


def _bars(n: int = 90) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    close = pd.Series(range(100, 100 + n), dtype=float)
    return pd.DataFrame(
        {
            "symbol": "000001.SZ",
            "date": dates,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000000.0,
            "amount": close * 1000000.0,
            "source": "test",
        }
    )


def test_signal_frame_adds_expected_columns() -> None:
    frame = _bars()
    result = build_signal_frame(frame)
    assert "score" in result.columns
    assert "signal" in result.columns
    assert "position_weight_cap" in result.columns
    assert len(result) == len(frame)

