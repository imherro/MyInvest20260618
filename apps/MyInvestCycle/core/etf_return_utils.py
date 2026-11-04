from __future__ import annotations

import pandas as pd


PRICE_RETURN_COLUMNS = ["trade_date", "close", "pre_close", "pct_chg"]


def coerce_price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=PRICE_RETURN_COLUMNS)

    result = frame.copy()
    for column in PRICE_RETURN_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    for column in ("close", "pre_close", "pct_chg"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
        result[column] = result[column].replace([float("inf"), float("-inf")], pd.NA)

    result = result.dropna(subset=["trade_date", "close"])
    result = result.sort_values("trade_date").reset_index(drop=True)
    return result[PRICE_RETURN_COLUMNS]


def daily_return_series(frame: pd.DataFrame) -> pd.Series:
    prices = coerce_price_frame(frame)
    if prices.empty:
        return pd.Series(dtype="float64")

    index = prices["trade_date"].astype(str)
    pct_returns = prices["pct_chg"] / 100.0
    pre_close_returns = prices["close"] / prices["pre_close"] - 1.0
    pre_close_returns = pre_close_returns.where(prices["pre_close"] > 0)
    close_returns = prices["close"].pct_change()

    returns = pct_returns.where(pct_returns.notna(), pre_close_returns)
    returns = returns.where(returns.notna(), close_returns)
    returns = pd.to_numeric(returns, errors="coerce").replace([float("inf"), float("-inf")], pd.NA)
    returns.index = index
    return returns.astype("float64")


def compound_recent_return(frame: pd.DataFrame, window: int) -> float | None:
    returns = daily_return_series(frame).dropna().tail(window)
    if len(returns) < window:
        return None
    return float((1.0 + returns).prod() - 1.0)
