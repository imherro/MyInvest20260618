from __future__ import annotations

import pandas as pd


def compute_market_features(daily: pd.DataFrame) -> dict[str, float | int]:
    if daily.empty:
        return _empty_features()

    frame = daily.copy()
    frame["pct_chg"] = pd.to_numeric(frame.get("pct_chg"), errors="coerce")
    frame["vol"] = pd.to_numeric(frame.get("vol"), errors="coerce")
    frame = frame.dropna(subset=["trade_date", "pct_chg"])
    if frame.empty:
        return _empty_features()

    by_date = (
        frame.groupby("trade_date", as_index=False)
        .agg(index_return=("pct_chg", "mean"), volume=("vol", "sum"))
        .sort_values("trade_date")
    )
    returns = by_date["index_return"] / 100.0
    volume = by_date["volume"]

    return {
        "observations": int(len(by_date)),
        "return_5d": _rolling_return(returns, 5),
        "return_20d": _rolling_return(returns, 20),
        "return_60d": _rolling_return(returns, 60),
        "volatility_20d": round(float(returns.tail(20).std() or 0), 6),
        "volume_trend_20d": _volume_trend(volume),
    }


def _rolling_return(returns: pd.Series, window: int) -> float:
    if returns.empty:
        return 0.0
    selected = returns.tail(min(window, len(returns)))
    cumulative = float((1 + selected).prod() - 1)
    return round(cumulative, 6)


def _volume_trend(volume: pd.Series) -> float:
    if len(volume) < 10:
        return 0.0
    recent = float(volume.tail(5).mean() or 0)
    baseline = float(volume.tail(20).head(15).mean() or 0)
    if baseline <= 0:
        return 0.0
    return round(recent / baseline - 1, 6)


def _empty_features() -> dict[str, float | int]:
    return {
        "observations": 0,
        "return_5d": 0.0,
        "return_20d": 0.0,
        "return_60d": 0.0,
        "volatility_20d": 0.0,
        "volume_trend_20d": 0.0,
    }
