from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from shortterm_trader.config import Settings, ensure_runtime_dirs
from shortterm_trader.data.providers import (
    BaoStockProvider,
    DataSourceError,
    FredProvider,
    TushareProvider,
    YFinanceProvider,
    first_success,
)
from shortterm_trader.symbols import is_a_share, normalize_symbol


@dataclass
class MarketDataRouter:
    settings: Settings

    def get_daily_bars(self, symbol: str, start: str, end: str, use_cache: bool = True) -> pd.DataFrame:
        ensure_runtime_dirs(self.settings)
        normalized = normalize_symbol(symbol)
        cache_path = self._cache_path(normalized, start, end)
        if use_cache and cache_path.exists():
            cached = _load_cached_bars(cache_path)
            cached.to_csv(cache_path, index=False, encoding="utf-8")
            return cached

        if is_a_share(normalized):
            _, bars = first_success(
                [
                    ("tushare", TushareProvider(self.settings)),
                    ("baostock", BaoStockProvider()),
                ],
                "fetch_daily",
                normalized,
                start,
                end,
            )
        else:
            _, bars = first_success([("yfinance", YFinanceProvider())], "fetch_daily", normalized, start, end)

        bars.insert(0, "symbol", normalized)
        bars.to_csv(cache_path, index=False, encoding="utf-8")
        return bars

    def get_fred_series(self, series_id: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        ensure_runtime_dirs(self.settings)
        provider = FredProvider(self.settings)
        try:
            return provider.fetch_series(series_id, start=start, end=end)
        except DataSourceError:
            raise

    def _cache_path(self, symbol: str, start: str, end: str) -> Path:
        safe_symbol = symbol.replace(".", "_").replace("^", "")
        return self.settings.cache_dir / f"{safe_symbol}_{start}_{end}.csv"


def _load_cached_bars(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"])
    return _repair_cached_amount_units(frame)


def _repair_cached_amount_units(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "amount" not in frame or "source" not in frame:
        return frame
    out = frame.copy()
    is_tushare = out["source"].astype(str).str.lower().eq("tushare")
    if not is_tushare.any():
        return out
    traded_value = pd.to_numeric(out.loc[is_tushare, "close"], errors="coerce") * pd.to_numeric(
        out.loc[is_tushare, "volume"], errors="coerce"
    )
    amount = pd.to_numeric(out.loc[is_tushare, "amount"], errors="coerce")
    ratio = (amount / traded_value.replace(0, pd.NA)).dropna()
    if not ratio.empty and 0 < float(ratio.median()) < 0.05:
        out.loc[is_tushare, "amount"] = amount * 1000
    return out
