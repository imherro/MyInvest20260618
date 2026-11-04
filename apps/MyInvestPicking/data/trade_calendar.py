from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd


def normalize_trade_date(value: str | None = None) -> str:
    if value is None:
        return date.today().strftime("%Y%m%d")

    raw = value.strip()
    if len(raw) == 8 and raw.isdigit():
        return raw
    return datetime.strptime(raw, "%Y-%m-%d").strftime("%Y%m%d")


def format_api_date(trade_date: str) -> str:
    return datetime.strptime(trade_date, "%Y%m%d").strftime("%Y-%m-%d")


def is_trading_day(value: str | None = None, calendar: pd.DataFrame | None = None) -> bool:
    trade_date = normalize_trade_date(value)
    if calendar is not None and not calendar.empty and "cal_date" in calendar.columns:
        matched = calendar[calendar["cal_date"].astype(str) == trade_date]
        if not matched.empty and "is_open" in matched.columns:
            return int(matched.iloc[-1]["is_open"]) == 1

    parsed = datetime.strptime(trade_date, "%Y%m%d")
    return parsed.weekday() < 5


def get_latest_trading_date(
    value: str | None = None,
    calendar: pd.DataFrame | None = None,
    max_lookback_days: int = 30,
) -> str:
    current = datetime.strptime(normalize_trade_date(value), "%Y%m%d")
    for _ in range(max_lookback_days + 1):
        candidate = current.strftime("%Y%m%d")
        if is_trading_day(candidate, calendar):
            return candidate
        current -= timedelta(days=1)
    return normalize_trade_date(value)
