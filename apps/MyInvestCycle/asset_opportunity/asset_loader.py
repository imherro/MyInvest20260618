from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from asset_opportunity.asset_schema import AssetRecord
from core.benchmark_loader import benchmark_cache_path, load_benchmark_daily, read_benchmark_cache
from core.data_loader import normalize_trade_date


OUTPUT_COLUMNS = ["trade_date", "close", "volume", "amount", "pct_chg", "pre_close"]


def _normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result["volume"] = pd.to_numeric(result["vol"] if "vol" in result else pd.NA, errors="coerce")
    result["amount"] = pd.to_numeric(result["amount"] if "amount" in result else pd.NA, errors="coerce")
    result["pct_chg"] = pd.to_numeric(result["pct_chg"] if "pct_chg" in result else pd.NA, errors="coerce")
    result["pre_close"] = pd.to_numeric(result["pre_close"] if "pre_close" in result else pd.NA, errors="coerce")
    result = result.dropna(subset=["trade_date", "close"])
    return result[OUTPUT_COLUMNS].sort_values("trade_date").reset_index(drop=True)


def load_asset_history(
    asset: AssetRecord | Mapping[str, object],
    start_date: str | int = "19000101",
    end_date: str | int = "20991231",
    *,
    cache_only: bool = True,
    refresh: bool = False,
) -> pd.DataFrame:
    record = asset if isinstance(asset, AssetRecord) else AssetRecord.from_mapping(asset)
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if record.type != "etf":
        raise ValueError(f"V3.1.1 only supports ETF fund_daily history for now: {record.code}")
    if cache_only:
        frame = read_benchmark_cache(record.code, start, end)
    else:
        frame = load_benchmark_daily(record.code, start, end, refresh=refresh, cache_only=False)
    return _normalize_history(frame)


def asset_history_coverage(
    asset: AssetRecord | Mapping[str, object],
    *,
    start_date: str | int = "19000101",
    end_date: str | int = "20991231",
) -> dict[str, object]:
    record = asset if isinstance(asset, AssetRecord) else AssetRecord.from_mapping(asset)
    cache_path = benchmark_cache_path(record.code)
    if not Path(cache_path).exists():
        return {
            "code": record.code,
            "name": record.name,
            "available": False,
            "cache_path": str(cache_path),
            "start": None,
            "end": None,
            "rows": 0,
            "missing_reason": "fund_daily cache missing",
        }
    frame = load_asset_history(record, start_date, end_date, cache_only=True)
    return {
        "code": record.code,
        "name": record.name,
        "available": not frame.empty,
        "cache_path": str(cache_path),
        "start": str(frame["trade_date"].iloc[0]) if not frame.empty else None,
        "end": str(frame["trade_date"].iloc[-1]) if not frame.empty else None,
        "rows": int(len(frame)),
        "columns": OUTPUT_COLUMNS,
    }
