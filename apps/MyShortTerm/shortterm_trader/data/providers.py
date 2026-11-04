from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from shortterm_trader.config import Settings
from shortterm_trader.symbols import to_baostock_code


class DataSourceError(RuntimeError):
    pass


REQUIRED_BAR_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount", "source"]


def normalize_bars(df: pd.DataFrame, source: str) -> pd.DataFrame:
    if df.empty:
        raise DataSourceError(f"{source} returned no rows")
    frame = df.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        if column not in frame:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["source"] = source
    frame = frame[REQUIRED_BAR_COLUMNS].dropna(subset=["date", "open", "high", "low", "close"])
    frame = frame.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    if frame.empty:
        raise DataSourceError(f"{source} rows could not be normalized")
    return frame.reset_index(drop=True)


@dataclass
class TushareProvider:
    settings: Settings

    def fetch_daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        if not self.settings.tushare_token:
            raise DataSourceError("TUSHARE_TOKEN is not configured")
        try:
            import tushare as ts
        except Exception as exc:  # pragma: no cover - import guard
            raise DataSourceError(f"tushare import failed: {exc}") from exc

        pro = ts.pro_api(self.settings.tushare_token)
        raw = pro.daily(ts_code=symbol, start_date=start, end_date=end)
        if raw is None or raw.empty:
            raise DataSourceError(f"Tushare returned no daily rows for {symbol}")
        frame = raw.rename(
            columns={
                "trade_date": "date",
                "vol": "volume",
            }
        )
        frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d")
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce") * 100
        frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce") * 1000
        return normalize_bars(frame, "tushare")


@dataclass
class BaoStockProvider:
    fields: str = "date,open,high,low,close,volume,amount,turn,pctChg"

    def fetch_daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        try:
            import baostock as bs
        except Exception as exc:  # pragma: no cover - import guard
            raise DataSourceError(f"baostock import failed: {exc}") from exc

        login_result = bs.login()
        if getattr(login_result, "error_code", "0") != "0":
            raise DataSourceError(f"BaoStock login failed: {login_result.error_msg}")
        try:
            rs = bs.query_history_k_data_plus(
                to_baostock_code(symbol),
                self.fields,
                start_date=_fmt_baostock_date(start),
                end_date=_fmt_baostock_date(end),
                frequency="d",
                adjustflag="2",
            )
            if getattr(rs, "error_code", "0") != "0":
                raise DataSourceError(f"BaoStock query failed: {rs.error_msg}")
            rows: list[list[str]] = []
            while rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                raise DataSourceError(f"BaoStock returned no rows for {symbol}")
            frame = pd.DataFrame(rows, columns=rs.fields)
            return normalize_bars(frame, "baostock")
        finally:
            bs.logout()


@dataclass
class YFinanceProvider:
    def fetch_daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except Exception as exc:  # pragma: no cover - import guard
            raise DataSourceError(f"yfinance import failed: {exc}") from exc

        raw = yf.download(symbol, start=_fmt_yf_date(start), end=_fmt_yf_date(end), progress=False)
        if raw is None or raw.empty:
            raise DataSourceError(f"yfinance returned no rows for {symbol}")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.reset_index()
        frame = raw.rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        frame["amount"] = frame["close"] * frame["volume"]
        return normalize_bars(frame, "yfinance")


@dataclass
class FredProvider:
    settings: Settings

    def fetch_series(self, series_id: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        if not self.settings.fred_api_key:
            raise DataSourceError("FRED_API_KEY is not configured")
        try:
            from fredapi import Fred
        except Exception as exc:  # pragma: no cover - import guard
            raise DataSourceError(f"fredapi import failed: {exc}") from exc

        fred = Fred(api_key=self.settings.fred_api_key)
        data = fred.get_series(series_id, observation_start=_fmt_fred_date(start), observation_end=_fmt_fred_date(end))
        if data is None or data.empty:
            raise DataSourceError(f"FRED returned no rows for {series_id}")
        return pd.DataFrame({"date": pd.to_datetime(data.index), "value": pd.to_numeric(data.values)})


def first_success(providers: Iterable[tuple[str, object]], method: str, *args: object) -> tuple[str, pd.DataFrame]:
    errors: list[str] = []
    for name, provider in providers:
        try:
            result = getattr(provider, method)(*args)
            return name, result
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise DataSourceError("; ".join(errors))


def _fmt_baostock_date(value: str) -> str:
    text = value.strip()
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) == 8 and text.isdigit() else text


def _fmt_yf_date(value: str) -> str:
    return _fmt_baostock_date(value)


def _fmt_fred_date(value: str | None) -> str | None:
    return _fmt_baostock_date(value) if value else None
