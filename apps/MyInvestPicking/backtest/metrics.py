from __future__ import annotations

from math import sqrt
from typing import Any

import pandas as pd


def calculate_metrics(
    equity_curve: list[dict[str, Any]],
    drawdown_curve: list[dict[str, Any]],
    turnover: float,
) -> dict[str, float]:
    if len(equity_curve) < 2:
        return {
            "cagr": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "turnover": turnover,
            "win_rate": 0.0,
        }

    nav = pd.Series([point["nav"] for point in equity_curve], dtype="float64")
    returns = nav.pct_change().dropna()
    years = max(len(nav) / 252, 1 / 252)
    cagr = float((nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1) if nav.iloc[0] else 0.0
    volatility = float(returns.std())
    sharpe = float(returns.mean() / volatility * sqrt(252)) if volatility > 0 else 0.0
    max_drawdown = min((point["drawdown"] for point in drawdown_curve), default=0.0)
    win_rate = float((returns > 0).mean()) if not returns.empty else 0.0
    return {
        "cagr": round(cagr, 6),
        "sharpe": round(sharpe, 6),
        "max_drawdown": round(max_drawdown, 6),
        "turnover": round(turnover, 6),
        "win_rate": round(win_rate, 6),
    }
