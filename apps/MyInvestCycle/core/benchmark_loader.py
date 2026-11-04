from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from config import CACHE_DIR
from core.data_loader import get_tushare_pro, normalize_trade_date
from core.etf_return_utils import daily_return_series


DEFAULT_BENCHMARK_CODE = "510500.SH"
BENCHMARK_DAILY_COLUMNS = [
    "ts_code",
    "trade_date",
    "close",
    "open",
    "high",
    "low",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
]
BENCHMARK_NUMERIC_COLUMNS = [
    "close",
    "open",
    "high",
    "low",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
]


def benchmark_cache_path(ts_code: str = DEFAULT_BENCHMARK_CODE, cache_dir: Path = CACHE_DIR) -> Path:
    safe_code = ts_code.replace(".", "_")
    return cache_dir / f"fund_daily_{safe_code}.csv"


def _empty_benchmark_daily() -> pd.DataFrame:
    return pd.DataFrame(columns=BENCHMARK_DAILY_COLUMNS)


def _coerce_benchmark_daily(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_benchmark_daily()

    result = df.copy()
    for column in BENCHMARK_DAILY_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    result = result[BENCHMARK_DAILY_COLUMNS]
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)

    for column in BENCHMARK_NUMERIC_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result = result.dropna(subset=["trade_date", "close"])
    result = result.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    result = result.sort_values("trade_date").reset_index(drop=True)
    return result


def _read_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return _empty_benchmark_daily()
    return _coerce_benchmark_daily(pd.read_csv(path, dtype={"trade_date": str}))


def read_benchmark_cache(
    ts_code: str = DEFAULT_BENCHMARK_CODE,
    start_date: str = "19000101",
    end_date: str = "20991231",
    *,
    cache_dir: Path = CACHE_DIR,
) -> pd.DataFrame:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date.")

    cached = _read_cache(benchmark_cache_path(ts_code, cache_dir))
    if cached.empty:
        return cached
    result = cached[(cached["trade_date"] >= start) & (cached["trade_date"] <= end)].copy()
    return result.sort_values("trade_date").reset_index(drop=True)


def _write_cache(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _coerce_benchmark_daily(df).to_csv(path, index=False, encoding="utf-8")


def _shift_date(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def _date_ranges_to_fetch(cached: pd.DataFrame, start_date: str, end_date: str) -> list[tuple[str, str]]:
    if cached.empty:
        return [(start_date, end_date)]

    cached_min = str(cached["trade_date"].min())
    cached_max = str(cached["trade_date"].max())
    ranges: list[tuple[str, str]] = []

    if start_date < cached_min:
        ranges.append((start_date, _shift_date(cached_min, -1)))
    if end_date > cached_max:
        ranges.append((_shift_date(cached_max, 1), end_date))

    return [(start, end) for start, end in ranges if start <= end]


def _combine_frames(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    valid_frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not valid_frames:
        return _empty_benchmark_daily()
    return _coerce_benchmark_daily(pd.concat(valid_frames, ignore_index=True))


def fetch_benchmark_daily(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    token: str | None = None,
) -> pd.DataFrame:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date.")

    pro = get_tushare_pro(token)
    raw = pro.fund_daily(ts_code=ts_code, start_date=start, end_date=end)
    return _coerce_benchmark_daily(raw)


def load_benchmark_daily(
    ts_code: str = DEFAULT_BENCHMARK_CODE,
    start_date: str = "20200101",
    end_date: str = "20991231",
    *,
    refresh: bool = False,
    cache_only: bool = False,
    token: str | None = None,
    cache_dir: Path = CACHE_DIR,
) -> pd.DataFrame:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date.")

    path = benchmark_cache_path(ts_code, cache_dir)
    cached = _empty_benchmark_daily() if refresh else _read_cache(path)

    fetch_ranges = [(start, end)] if refresh else _date_ranges_to_fetch(cached, start, end)
    fetched_frames: list[pd.DataFrame] = []
    if fetch_ranges and cache_only:
        missing = ", ".join(f"{fetch_start}-{fetch_end}" for fetch_start, fetch_end in fetch_ranges)
        raise FileNotFoundError(f"benchmark cache missing ranges for {ts_code}: {missing}")

    for fetch_start, fetch_end in fetch_ranges:
        fetched_frames.append(fetch_benchmark_daily(ts_code, fetch_start, fetch_end, token=token))

    combined = _combine_frames([cached, *fetched_frames])
    if not combined.empty and fetched_frames:
        _write_cache(path, combined)

    result = combined[(combined["trade_date"] >= start) & (combined["trade_date"] <= end)].copy()
    return result.sort_values("trade_date").reset_index(drop=True)


def benchmark_returns_frame(benchmark_daily: pd.DataFrame) -> pd.DataFrame:
    df = _coerce_benchmark_daily(benchmark_daily)
    if df.empty:
        return pd.DataFrame(columns=["date", "benchmark_close", "benchmark_return", "benchmark_equity"])

    result = pd.DataFrame(
        {
            "date": df["trade_date"].astype(str),
            "benchmark_close": df["close"].astype(float),
        }
    )
    result["benchmark_return"] = daily_return_series(df).reset_index(drop=True).fillna(0.0)
    if not result.empty:
        result.loc[result.index[0], "benchmark_return"] = 0.0
    result["benchmark_equity"] = (1.0 + result["benchmark_return"]).cumprod()
    return result.reset_index(drop=True)
