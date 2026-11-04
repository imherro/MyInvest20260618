from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import CACHE_DIR, DEFAULT_INDEX_CODE
from core.breadth import get_market_daily, get_market_history_sample
from core.data_loader import get_index_daily, normalize_trade_date
from core.liquidity import get_moneyflow_hsgt
from core.regime_adapter import adapt_regime_payload
from engine.market_engine import analyze_index_regime


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def _market_daily_cache_path(trade_date: str) -> Path:
    return CACHE_DIR / f"market_daily_{trade_date}.csv"


def load_regime_payload(
    trade_date: str,
    *,
    ts_code: str = DEFAULT_INDEX_CODE,
    refresh: bool = False,
    cache_only: bool = False,
    include_hsgt: bool = False,
    history_sample_size: int = 0,
) -> dict[str, object]:
    date_text = normalize_trade_date(trade_date)
    warmup_start = _calendar_shift(date_text, -540)
    index_df = get_index_daily(ts_code, warmup_start, date_text, refresh=refresh)
    if index_df.empty:
        raise RuntimeError("No index rows available for regime input bridge.")

    index_df = index_df[index_df["trade_date"].astype(str) <= date_text].copy()
    if index_df.empty:
        raise RuntimeError(f"No index rows on or before {date_text}.")
    as_of = str(index_df["trade_date"].iloc[-1])

    if cache_only and not _market_daily_cache_path(as_of).exists():
        raise FileNotFoundError(f"market_daily cache missing for {as_of}")
    market_daily = get_market_daily(as_of, refresh=refresh)

    market_history = None
    if history_sample_size > 0:
        market_history = get_market_history_sample(
            market_daily,
            _calendar_shift(as_of, -370),
            as_of,
            sample_size=history_sample_size,
        )

    hsgt_df = None
    if include_hsgt:
        hsgt_start = str(index_df["trade_date"].tail(30).iloc[0])
        hsgt_df = get_moneyflow_hsgt(hsgt_start, as_of, refresh=refresh)

    return analyze_index_regime(
        index_df,
        market_daily_df=market_daily,
        market_history_df=market_history,
        hsgt_df=hsgt_df,
    )


def load_risk_input_signal(
    trade_date: str,
    *,
    ts_code: str = DEFAULT_INDEX_CODE,
    refresh: bool = False,
    cache_only: bool = False,
    include_hsgt: bool = False,
    history_sample_size: int = 0,
) -> dict[str, object]:
    payload = load_regime_payload(
        trade_date,
        ts_code=ts_code,
        refresh=refresh,
        cache_only=cache_only,
        include_hsgt=include_hsgt,
        history_sample_size=history_sample_size,
    )
    return adapt_regime_payload(payload)
