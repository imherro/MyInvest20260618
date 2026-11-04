from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from config import DATA_DIR
from core.benchmark_loader import load_benchmark_daily, read_benchmark_cache
from core.data_loader import (
    cache_path_for,
    get_index_daily,
    get_tushare_pro,
    normalize_trade_date,
)


INDUSTRY_DATA_DIR = DATA_DIR / "industry"
SW2021_SOURCE = "SW2021"
SW2021_LEVEL = "L1"


@dataclass(frozen=True)
class IndustryAsset:
    code: str
    name: str
    source_type: str
    source: str


ETF_PROXY_UNIVERSE: tuple[IndustryAsset, ...] = (
    IndustryAsset("512000.SH", "券商ETF", "etf_proxy", "fund_daily"),
    IndustryAsset("512800.SH", "银行ETF", "etf_proxy", "fund_daily"),
    IndustryAsset("512690.SH", "酒ETF", "etf_proxy", "fund_daily"),
    IndustryAsset("512480.SH", "半导体ETF", "etf_proxy", "fund_daily"),
    IndustryAsset("512170.SH", "医疗ETF", "etf_proxy", "fund_daily"),
    IndustryAsset("512660.SH", "军工ETF", "etf_proxy", "fund_daily"),
    IndustryAsset("515790.SH", "光伏ETF", "etf_proxy", "fund_daily"),
    IndustryAsset("516160.SH", "新能源ETF", "etf_proxy", "fund_daily"),
    IndustryAsset("515000.SH", "科技ETF", "etf_proxy", "fund_daily"),
    IndustryAsset("588000.SH", "科创50ETF", "etf_proxy", "fund_daily"),
)


def _universe_cache_path(
    source: str = SW2021_SOURCE,
    level: str = SW2021_LEVEL,
    data_dir: Path = INDUSTRY_DATA_DIR,
) -> Path:
    return data_dir / f"industry_universe_{source}_{level}.json"


def _serialize_assets(assets: list[IndustryAsset], metadata: Mapping[str, object]) -> dict[str, object]:
    return {
        "metadata": dict(metadata),
        "assets": [asdict(asset) for asset in assets],
    }


def _load_assets_from_payload(payload: Mapping[str, object]) -> list[IndustryAsset]:
    rows = payload.get("assets") or []
    assets: list[IndustryAsset] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        assets.append(
            IndustryAsset(
                code=str(row["code"]),
                name=str(row["name"]),
                source_type=str(row["source_type"]),
                source=str(row["source"]),
            )
        )
    return assets


def _read_universe_cache(path: Path) -> tuple[list[IndustryAsset], dict[str, object]] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    assets = _load_assets_from_payload(payload)
    return assets, dict(payload.get("metadata") or {})


def _write_universe_cache(path: Path, assets: list[IndustryAsset], metadata: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _serialize_assets(assets, metadata)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_sw2021_l1_universe(*, token: str | None = None) -> list[IndustryAsset]:
    pro = get_tushare_pro(token)
    raw = pro.index_classify(level=SW2021_LEVEL, src=SW2021_SOURCE)
    if raw is None or raw.empty:
        raise RuntimeError("Tushare index_classify returned no SW2021 L1 industries.")
    required = {"index_code", "industry_name"}
    missing = required - set(raw.columns)
    if missing:
        raise RuntimeError(f"Tushare index_classify missing columns: {', '.join(sorted(missing))}")

    rows = raw.dropna(subset=["index_code", "industry_name"]).copy()
    rows = rows.sort_values("index_code")
    return [
        IndustryAsset(
            code=str(row["index_code"]),
            name=str(row["industry_name"]),
            source_type="industry_index",
            source="tushare.index_classify:index_daily:SW2021:L1",
        )
        for _, row in rows.iterrows()
    ]


def load_industry_universe(
    *,
    refresh: bool = False,
    allow_etf_proxy: bool = True,
    token: str | None = None,
) -> tuple[list[IndustryAsset], dict[str, object]]:
    path = _universe_cache_path()
    if not refresh:
        cached = _read_universe_cache(path)
        if cached:
            assets, metadata = cached
            metadata = {**metadata, "cache_path": str(path), "loaded_from_cache": True}
            return assets, metadata

    try:
        assets = fetch_sw2021_l1_universe(token=token)
    except Exception as exc:
        cached = _read_universe_cache(path)
        if cached:
            assets, metadata = cached
            metadata = {
                **metadata,
                "cache_path": str(path),
                "loaded_from_cache": True,
                "refresh_error": str(exc),
            }
            return assets, metadata
        if not allow_etf_proxy:
            raise
        return list(ETF_PROXY_UNIVERSE), {
            "source_type": "etf_proxy",
            "provider": "Tushare fund_daily",
            "fallback_reason": str(exc),
            "loaded_from_cache": False,
        }

    metadata = {
        "source_type": "industry_index",
        "provider": "Tushare",
        "source": "index_classify",
        "index_daily_source": "index_daily",
        "universe": f"{SW2021_SOURCE} {SW2021_LEVEL}",
        "industry_count": len(assets),
        "loaded_from_cache": False,
    }
    _write_universe_cache(path, assets, metadata)
    return assets, {**metadata, "cache_path": str(path)}


def _read_index_cache_only(asset: IndustryAsset, start_date: str, end_date: str) -> pd.DataFrame:
    path = cache_path_for(asset.code)
    if not path.exists():
        raise FileNotFoundError(f"index cache missing for {asset.code}: {path}")
    df = pd.read_csv(path, dtype={"trade_date": str})
    df["trade_date"] = df["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result = df[(df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)].copy()
    return result.sort_values("trade_date").reset_index(drop=True)


def load_asset_history(
    asset: IndustryAsset,
    start_date: str | int,
    end_date: str | int,
    *,
    refresh: bool = False,
    cache_only: bool = False,
    token: str | None = None,
) -> pd.DataFrame:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if asset.source_type == "industry_index":
        if cache_only:
            return _read_index_cache_only(asset, start, end)
        return get_index_daily(asset.code, start, end, refresh=refresh, token=token)

    if cache_only:
        return read_benchmark_cache(asset.code, start, end)
    return load_benchmark_daily(asset.code, start, end, refresh=refresh, token=token)


def load_industry_panel(
    start_date: str | int,
    end_date: str | int,
    *,
    refresh_universe: bool = False,
    refresh_prices: bool = False,
    cache_only: bool = False,
    allow_etf_proxy: bool = True,
    token: str | None = None,
) -> tuple[list[IndustryAsset], dict[str, pd.DataFrame], dict[str, object]]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    assets, universe_status = load_industry_universe(
        refresh=refresh_universe,
        allow_etf_proxy=allow_etf_proxy,
        token=token,
    )
    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for asset in assets:
        try:
            frame = load_asset_history(
                asset,
                start,
                end,
                refresh=refresh_prices,
                cache_only=cache_only,
                token=token,
            )
        except Exception as exc:
            errors[asset.code] = str(exc)
            continue
        if frame.empty:
            errors[asset.code] = "empty history"
            continue
        frames[asset.code] = frame

    status = {
        "universe": universe_status,
        "requested_range": {"start_date": start, "end_date": end},
        "asset_count": len(assets),
        "available_count": len(frames),
        "errors": errors,
        "source_type": str(universe_status.get("source_type") or (assets[0].source_type if assets else "unknown")),
    }
    return assets, frames, status
