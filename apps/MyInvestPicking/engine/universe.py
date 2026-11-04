from __future__ import annotations

import pandas as pd


ST_PATTERN = r"(?:^|\*)ST|退|退市"


def add_tradeability_flags(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily.copy()

    flagged = daily.copy()
    pct_chg = pd.to_numeric(flagged.get("pct_chg"), errors="coerce")
    flagged["is_limit_up"] = pct_chg >= 9.8
    flagged["is_limit_down"] = pct_chg <= -9.8
    if "is_suspended" not in flagged.columns:
        flagged["is_suspended"] = False
    flagged["is_tradeable"] = (
        (flagged["is_suspended"] != True)  # noqa: E712
        & ~flagged["is_limit_up"]
        & ~flagged["is_limit_down"]
    )
    return flagged


def filter_universe(stock_basic: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    if stock_basic.empty:
        return stock_basic.copy()

    filtered = stock_basic.copy()
    names = filtered["name"].fillna("").astype(str)
    filtered = filtered[~names.str.contains(ST_PATTERN, case=False, regex=True)]

    daily = add_tradeability_flags(daily)
    if daily.empty or "ts_code" not in daily.columns:
        return filtered.reset_index(drop=True)

    latest_trade_date = daily["trade_date"].max()
    latest_daily = daily[daily["trade_date"] == latest_trade_date]
    if "is_suspended" in latest_daily.columns:
        latest_daily = latest_daily[latest_daily["is_suspended"] != True]  # noqa: E712
    if "is_tradeable" in latest_daily.columns:
        latest_daily = latest_daily[latest_daily["is_tradeable"] == True]  # noqa: E712

    tradable_codes = set(latest_daily["ts_code"].dropna().astype(str))
    filtered = filtered[filtered["ts_code"].isin(tradable_codes)]
    return filtered.reset_index(drop=True)
