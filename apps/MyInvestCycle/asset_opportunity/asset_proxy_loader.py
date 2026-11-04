from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from asset_opportunity.asset_loader import OUTPUT_COLUMNS, load_asset_history
from asset_opportunity.asset_proxy_schema import AssetProxyRecord
from config import BASE_DIR
from core.data_loader import cache_path_for, get_index_daily, normalize_trade_date


def _normalize_index_history(frame: pd.DataFrame) -> pd.DataFrame:
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


def _read_index_cache(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    path = cache_path_for(code)
    if not Path(path).exists():
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    frame = pd.read_csv(path, dtype={"trade_date": str})
    normalized = _normalize_index_history(frame)
    return normalized[(normalized["trade_date"] >= start_date) & (normalized["trade_date"] <= end_date)].reset_index(drop=True)


def _project_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def load_research_proxy_history(
    mapping: AssetProxyRecord | Mapping[str, object],
    start_date: str | int = "19000101",
    end_date: str | int = "20991231",
    *,
    cache_only: bool = True,
) -> pd.DataFrame:
    record = mapping if isinstance(mapping, AssetProxyRecord) else AssetProxyRecord.from_mapping(mapping)
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if record.research_proxy is None:
        return load_asset_history(
            {
                "code": record.asset_code,
                "name": record.asset_name,
                "type": record.asset_type,
                "category": record.asset_category,
                "source": "Tushare fund_daily",
                "benchmark": record.asset_code,
                "enabled": record.enabled,
            },
            start,
            end,
            cache_only=cache_only,
        )
    if cache_only:
        return _read_index_cache(record.research_proxy.code, start, end)
    return _normalize_index_history(get_index_daily(record.research_proxy.code, start, end))


def research_proxy_coverage(
    mapping: AssetProxyRecord | Mapping[str, object],
    *,
    start_date: str | int = "19000101",
    end_date: str | int = "20991231",
) -> dict[str, object]:
    record = mapping if isinstance(mapping, AssetProxyRecord) else AssetProxyRecord.from_mapping(mapping)
    if record.research_proxy is None:
        return {
            "asset_code": record.asset_code,
            "asset_name": record.asset_name,
            "mapping_method": record.mapping_method,
            "has_proxy": False,
            "available": False,
            "proxy_code": None,
            "proxy_name": None,
            "start": None,
            "end": None,
            "rows": 0,
        }
    path = cache_path_for(record.research_proxy.code)
    frame = load_research_proxy_history(record, start_date, end_date, cache_only=True)
    return {
        "asset_code": record.asset_code,
        "asset_name": record.asset_name,
        "mapping_method": record.mapping_method,
        "has_proxy": True,
        "available": not frame.empty,
        "proxy_code": record.research_proxy.code,
        "proxy_name": record.research_proxy.name,
        "proxy_type": record.research_proxy.type,
        "proxy_source": record.research_proxy.source,
        "cache_path": _project_path(path),
        "start": str(frame["trade_date"].iloc[0]) if not frame.empty else None,
        "end": str(frame["trade_date"].iloc[-1]) if not frame.empty else None,
        "rows": int(len(frame)),
    }
