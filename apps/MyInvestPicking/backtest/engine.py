from __future__ import annotations

from typing import Any

from backtest.metrics import calculate_metrics
from backtest.portfolio_state import simulate_portfolio_state
from engine.data_loader import MarketData


def run_backtest(
    market_data: MarketData,
    positions: list[dict[str, Any]],
    lookback_days: int = 30,
) -> dict[str, Any]:
    state = simulate_portfolio_state(
        market_data.daily,
        positions,
        lookback_days=lookback_days,
    )
    metrics = calculate_metrics(
        state["equity_curve"],
        state["drawdown_curve"],
        state["turnover"],
    )
    return {
        "lookback_days": lookback_days,
        "assumptions": {
            "rebalance": "daily_to_target_weights",
            "transaction_cost": 0.001,
            "slippage": 0.0015,
            "initial_nav": 1.0,
        },
        "metrics": metrics,
        "equity_curve": state["equity_curve"],
        "drawdown_curve": state["drawdown_curve"],
    }
