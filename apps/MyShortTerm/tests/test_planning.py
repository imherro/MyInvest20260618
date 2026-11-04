import pandas as pd

from shortterm_trader.planning import TradeFilterParams, build_next_day_plan


def _bars(symbol: str = "000001.SZ", n: int = 90) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    close = pd.Series([10 + i * 0.08 for i in range(n)], dtype=float)
    volume = pd.Series([1_000_000.0] * n)
    volume.iloc[-1] = 2_000_000.0
    return pd.DataFrame(
        {
            "symbol": symbol,
            "date": dates,
            "open": close - 0.05,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": volume,
            "amount": close * volume * 100,
            "source": "test",
        }
    )


def test_build_next_day_plan_returns_ranked_actions() -> None:
    universe = [{"symbol": "000001.SZ", "name": "平安银行"}]
    plan = build_next_day_plan(universe, {"000001.SZ": _bars()}, params=TradeFilterParams(min_amount=1))
    assert len(plan) == 1
    assert plan.iloc[0]["symbol"] == "000001.SZ"
    assert plan.iloc[0]["action"] in {"candidate", "watch_if_trigger", "filtered", "blocked"}
    assert "trigger_price" in plan.columns

