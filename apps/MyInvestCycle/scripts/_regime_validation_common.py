from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DEFAULT_INDEX_CODE
from core.breadth import get_market_daily, get_market_history_sample
from core.data_loader import get_index_daily
from core.liquidity import get_moneyflow_hsgt
from engine.market_engine import analyze_index_regime
from engine_test import build_sample_hsgt, build_sample_index_daily, build_sample_market_daily


@dataclass
class RegimeContext:
    index_df: pd.DataFrame
    market_daily_df: pd.DataFrame
    hsgt_df: pd.DataFrame | None
    market_history_df: pd.DataFrame | None = None


def _history_start(as_of: str) -> str:
    return (pd.to_datetime(as_of, format="%Y%m%d") - pd.Timedelta(days=370)).strftime("%Y%m%d")


def load_sample_context() -> RegimeContext:
    index_df = build_sample_index_daily()
    market_daily_df = build_sample_market_daily(str(index_df["trade_date"].iloc[-1]))
    hsgt_df = build_sample_hsgt(index_df["trade_date"])
    return RegimeContext(index_df=index_df, market_daily_df=market_daily_df, hsgt_df=hsgt_df)


def load_live_context(
    *,
    ts_code: str = DEFAULT_INDEX_CODE,
    start_date: str = "20250101",
    end_date: str | None = None,
    history_sample_size: int = 0,
) -> RegimeContext:
    end = end_date or date.today().strftime("%Y%m%d")
    index_df = get_index_daily(ts_code, start_date, end)
    if index_df.empty:
        raise RuntimeError("No index rows returned from Tushare.")
    as_of = str(index_df["trade_date"].iloc[-1])
    market_daily_df = get_market_daily(as_of)
    hsgt_df = get_moneyflow_hsgt(str(index_df["trade_date"].iloc[-30]), as_of)
    market_history_df = None
    if history_sample_size > 0:
        market_history_df = get_market_history_sample(
            market_daily_df,
            _history_start(as_of),
            as_of,
            sample_size=history_sample_size,
        )
    return RegimeContext(
        index_df=index_df,
        market_daily_df=market_daily_df,
        hsgt_df=hsgt_df,
        market_history_df=market_history_df,
    )


def run_context(context: RegimeContext) -> dict:
    return analyze_index_regime(
        context.index_df.copy(),
        market_daily_df=context.market_daily_df.copy(),
        market_history_df=None if context.market_history_df is None else context.market_history_df.copy(),
        hsgt_df=None if context.hsgt_df is None else context.hsgt_df.copy(),
    )


def perturb_context(context: RegimeContext, close_multiplier: float) -> RegimeContext:
    index_df = context.index_df.copy()
    for column in ("close", "open", "high", "low"):
        if column in index_df.columns:
            index_df[column] = index_df[column] * close_multiplier
    return RegimeContext(
        index_df=index_df,
        market_daily_df=context.market_daily_df.copy(),
        hsgt_df=None if context.hsgt_df is None else context.hsgt_df.copy(),
        market_history_df=None if context.market_history_df is None else context.market_history_df.copy(),
    )
