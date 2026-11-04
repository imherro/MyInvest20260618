from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from config import CACHE_DIR, TUSHARE_TOKEN


INDEX_DAILY_COLUMNS = [
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

NUMERIC_COLUMNS = [
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


def normalize_trade_date(value: str | int | pd.Timestamp) -> str:
    """Normalize dates to Tushare's YYYYMMDD format."""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y%m%d")

    text = str(value).strip().replace("-", "").replace("/", "")
    if not re.fullmatch(r"\d{8}", text):
        raise ValueError(f"Invalid trade date: {value!r}. Expected YYYYMMDD.")
    return text


def cache_path_for(ts_code: str, cache_dir: Path = CACHE_DIR) -> Path:
    safe_code = ts_code.replace(".", "_")
    return cache_dir / f"index_daily_{safe_code}.csv"


def _empty_index_daily() -> pd.DataFrame:
    return pd.DataFrame(columns=INDEX_DAILY_COLUMNS)


def _coerce_index_daily(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_index_daily()

    result = df.copy()
    for column in INDEX_DAILY_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    result = result[INDEX_DAILY_COLUMNS]
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)

    for column in NUMERIC_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result = result.dropna(subset=["trade_date", "close"])
    result = result.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    result = result.sort_values("trade_date").reset_index(drop=True)
    return result


def _read_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return _empty_index_daily()
    return _coerce_index_daily(pd.read_csv(path, dtype={"trade_date": str}))


def _write_cache(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _coerce_index_daily(df).to_csv(path, index=False, encoding="utf-8")


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
        return _empty_index_daily()
    return _coerce_index_daily(pd.concat(valid_frames, ignore_index=True))


def get_tushare_pro(token: str | None = None):
    resolved_token = token or TUSHARE_TOKEN
    if not resolved_token:
        raise RuntimeError("TUSHARE_TOKEN is not configured. Add it to .env or the environment.")

    try:
        import tushare as ts
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("tushare is not installed. Install dependencies from requirements.txt.") from exc

    ts.set_token(resolved_token)
    return ts.pro_api()


def fetch_index_daily(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    token: str | None = None,
) -> pd.DataFrame:
    """Fetch index daily data from Tushare without touching local cache."""
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date.")

    pro = get_tushare_pro(token)
    raw = pro.index_daily(ts_code=ts_code, start_date=start, end_date=end)
    return _coerce_index_daily(raw)


def get_index_daily(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    refresh: bool = False,
    token: str | None = None,
    cache_dir: Path = CACHE_DIR,
) -> pd.DataFrame:
    """Return cached index daily data, fetching missing outer ranges from Tushare."""
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date.")

    path = cache_path_for(ts_code, cache_dir)
    cached = _empty_index_daily() if refresh else _read_cache(path)

    fetch_ranges = [(start, end)] if refresh else _date_ranges_to_fetch(cached, start, end)
    fetched_frames = [
        fetch_index_daily(ts_code, fetch_start, fetch_end, token=token)
        for fetch_start, fetch_end in fetch_ranges
    ]

    combined = _combine_frames([cached, *fetched_frames])
    if not combined.empty:
        _write_cache(path, combined)

    result = combined[(combined["trade_date"] >= start) & (combined["trade_date"] <= end)].copy()
    return result.sort_values("trade_date").reset_index(drop=True)
