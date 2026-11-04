import pandas as pd

from shortterm_trader.backtest import run_backtest


def test_backtest_returns_metrics() -> None:
    dates = pd.date_range("2026-01-01", periods=90, freq="B")
    close = pd.Series([100 + i * 0.5 for i in range(90)], dtype=float)
    bars = pd.DataFrame(
        {
            "symbol": "000001.SZ",
            "date": dates,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000000,
            "amount": close * 1000000,
            "source": "test",
        }
    )
    frame, metrics = run_backtest(bars)
    assert not frame.empty
    assert "total_return" in metrics
    assert "max_drawdown" in metrics

