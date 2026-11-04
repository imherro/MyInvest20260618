from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from shortterm_trader.strategy.indicators import max_drawdown
from shortterm_trader.strategy.short_term import StrategyParams, build_signal_frame


@dataclass(frozen=True)
class BacktestParams:
    cost_bps: float = 5.0
    strategy: StrategyParams = StrategyParams()


def run_backtest(bars: pd.DataFrame, params: BacktestParams | None = None) -> tuple[pd.DataFrame, dict[str, float]]:
    cfg = params or BacktestParams()
    frame = build_signal_frame(bars, params=cfg.strategy)
    frame["asset_return"] = frame["close"].pct_change().fillna(0)
    frame["position"] = frame["signal"].shift(1).fillna(False).astype(float)
    frame["trade"] = frame["position"].diff().abs().fillna(frame["position"])
    frame["cost"] = frame["trade"] * cfg.cost_bps / 10000
    frame["strategy_return"] = frame["position"] * frame["asset_return"] - frame["cost"]
    frame["equity"] = (1 + frame["strategy_return"]).cumprod()

    active = frame.loc[frame["position"] > 0, "strategy_return"]
    metrics = {
        "total_return": float(frame["equity"].iloc[-1] - 1),
        "max_drawdown": max_drawdown(frame["equity"]),
        "exposure": float(frame["position"].mean()),
        "trades": float(frame["trade"].sum() / 2),
        "win_rate": float((active > 0).mean()) if len(active) else 0.0,
        "avg_daily_return": float(frame["strategy_return"].mean()),
        "daily_volatility": float(frame["strategy_return"].std(ddof=0)),
    }
    metrics["simple_sharpe"] = (
        metrics["avg_daily_return"] / metrics["daily_volatility"] * (252**0.5)
        if metrics["daily_volatility"]
        else 0.0
    )
    return frame, metrics

