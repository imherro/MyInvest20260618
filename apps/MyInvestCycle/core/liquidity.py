from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import CACHE_DIR
from core.data_loader import get_tushare_pro, normalize_trade_date


HSGT_COLUMNS = [
    "trade_date",
    "ggt_ss",
    "ggt_sz",
    "hgt",
    "sgt",
    "north_money",
    "south_money",
]


def _cache_path(start_date: str, end_date: str, cache_dir: Path = CACHE_DIR) -> Path:
    return cache_dir / f"moneyflow_hsgt_{start_date}_{end_date}.csv"


def _coerce_hsgt(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=HSGT_COLUMNS)

    result = df.copy()
    for column in HSGT_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    result = result[HSGT_COLUMNS]
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    for column in HSGT_COLUMNS:
        if column != "trade_date":
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.sort_values("trade_date").reset_index(drop=True)


def fetch_moneyflow_hsgt(
    start_date: str,
    end_date: str,
    *,
    token: str | None = None,
) -> pd.DataFrame:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    pro = get_tushare_pro(token)
    raw = pro.moneyflow_hsgt(start_date=start, end_date=end)
    return _coerce_hsgt(raw)


def get_moneyflow_hsgt(
    start_date: str,
    end_date: str,
    *,
    refresh: bool = False,
    token: str | None = None,
    cache_dir: Path = CACHE_DIR,
) -> pd.DataFrame:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    path = _cache_path(start, end, cache_dir)
    if path.exists() and not refresh:
        return _coerce_hsgt(pd.read_csv(path, dtype={"trade_date": str}))

    df = fetch_moneyflow_hsgt(start, end, token=token)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    return df


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        raise ValueError("high must be greater than low")
    return max(0.0, min(1.0, (value - low) / (high - low)))


def calculate_liquidity_metrics(
    index_df: pd.DataFrame,
    *,
    hsgt_df: pd.DataFrame | None = None,
    volume_window: int = 20,
) -> dict[str, float | None]:
    if index_df.empty:
        raise ValueError("index_df is empty")

    df = index_df.copy()
    value_column = "amount" if "amount" in df.columns else "vol"
    if value_column not in df.columns:
        raise KeyError("index_df must contain amount or vol for liquidity scoring")

    df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
    df = df.dropna(subset=[value_column])
    if len(df) < max(5, volume_window // 2):
        raise ValueError("Not enough index rows for liquidity scoring")

    latest_value = float(df[value_column].iloc[-1])
    ma_value = float(df[value_column].rolling(volume_window, min_periods=max(5, volume_window // 2)).mean().iloc[-1])
    turnover_ma_ratio = latest_value / ma_value if ma_value else 0.0
    turnover_score = _scale(turnover_ma_ratio, 0.70, 1.40)

    northbound_5d_avg: float | None = None
    northbound_score: float | None = None
    if hsgt_df is not None and not hsgt_df.empty:
        hsgt = _coerce_hsgt(hsgt_df).dropna(subset=["north_money"])
        if not hsgt.empty:
            northbound_5d_avg = float(hsgt["north_money"].tail(5).mean())
            northbound_score = _scale(northbound_5d_avg, -50.0, 100.0)

    if northbound_score is None:
        liquidity_score = turnover_score
    else:
        liquidity_score = 0.65 * turnover_score + 0.35 * northbound_score

    return {
        "turnover_ma_ratio": round(turnover_ma_ratio, 4),
        "northbound_5d_avg": None if northbound_5d_avg is None else round(northbound_5d_avg, 4),
        "liquidity_score": round(max(0.0, min(1.0, liquidity_score)), 4),
    }
