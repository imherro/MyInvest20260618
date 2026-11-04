from __future__ import annotations

from typing import Any

import pandas as pd

from backtest.execution_simulator import execution_cost


def simulate_portfolio_state(
    daily: pd.DataFrame,
    positions: list[dict[str, Any]],
    lookback_days: int = 30,
    initial_nav: float = 1.0,
) -> dict[str, Any]:
    if daily.empty or not positions:
        return {"equity_curve": [], "drawdown_curve": [], "turnover": 0.0}

    target_weights = {position["code"]: float(position.get("weight") or 0) for position in positions}
    frame = daily[daily["ts_code"].isin(target_weights)].copy()
    frame["pct_chg"] = pd.to_numeric(frame.get("pct_chg"), errors="coerce").fillna(0) / 100.0
    returns = (
        frame.pivot_table(index="trade_date", columns="ts_code", values="pct_chg")
        .fillna(0)
        .tail(lookback_days)
    )
    if returns.empty:
        return {"equity_curve": [], "drawdown_curve": [], "turnover": 0.0}

    nav = initial_nav
    peak = initial_nav
    total_turnover = 0.0
    equity_curve = []
    drawdown_curve = []
    current_weights = {code: 0.0 for code in target_weights}

    for trade_date, row in returns.iterrows():
        turnover = sum(abs(target_weights[code] - current_weights.get(code, 0.0)) for code in target_weights) / 2
        total_turnover += turnover
        cost = execution_cost(turnover)
        portfolio_return = sum(target_weights[code] * float(row.get(code, 0.0)) for code in target_weights)
        nav = nav * (1 + portfolio_return - cost)
        peak = max(peak, nav)
        drawdown = nav / peak - 1 if peak else 0.0
        equity_curve.append({"date": _format_date(str(trade_date)), "nav": round(nav, 6)})
        drawdown_curve.append({"date": _format_date(str(trade_date)), "drawdown": round(drawdown, 6)})
        current_weights = _drift_weights(target_weights, row)

    return {
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "turnover": round(total_turnover, 6),
    }


def _drift_weights(target_weights: dict[str, float], returns: pd.Series) -> dict[str, float]:
    drifted = {
        code: target_weights[code] * (1 + float(returns.get(code, 0.0)))
        for code in target_weights
    }
    total = sum(drifted.values())
    if total <= 0:
        return {code: 0.0 for code in target_weights}
    return {code: weight / total for code, weight in drifted.items()}


def _format_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value
