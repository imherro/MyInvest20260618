import pandas as pd

from shortterm_trader.data.store import SQLiteDataStore


def test_store_upserts_and_loads_daily_bars(tmp_path) -> None:
    store = SQLiteDataStore(tmp_path / "shortterm.sqlite")
    bars = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000001.SZ"],
            "date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
            "open": [10.0, 10.2],
            "high": [10.5, 10.8],
            "low": [9.9, 10.1],
            "close": [10.4, 10.7],
            "volume": [1000.0, 1200.0],
            "amount": [100000000.0, 130000000.0],
            "source": ["test", "test"],
        }
    )

    assert store.upsert_daily_bars(bars) == 2
    loaded = store.load_daily_bars("000001.SZ")
    assert len(loaded) == 2
    assert list(loaded["close"]) == [10.4, 10.7]
    coverage = store.coverage()
    assert coverage.iloc[0]["symbol"] == "000001.SZ"
    assert int(coverage.iloc[0]["rows"]) == 2

