from __future__ import annotations

from typing import Mapping

import pandas as pd

from core.alpha_validation_engine import (
    annualized_return,
    annualized_volatility,
    compound_return,
    hit_rate,
    max_drawdown,
    sharpe_ratio,
)


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def calmar_ratio(annualized: float | None, drawdown: float | None) -> float | None:
    if annualized is None or drawdown is None or drawdown == 0:
        return None
    return float(annualized) / abs(float(drawdown))


def metrics_for_returns(returns: pd.Series) -> dict[str, object]:
    clean = returns.fillna(0.0)
    equity = (1.0 + clean).cumprod()
    total = compound_return(clean)
    annualized = annualized_return(total, len(clean))
    drawdown = max_drawdown(equity)
    return {
        "sessions": int(len(clean)),
        "total_return": _round(total),
        "annualized_return": _round(annualized),
        "annualized_volatility": _round(annualized_volatility(clean)),
        "sharpe": _round(sharpe_ratio(clean)),
        "max_drawdown": drawdown,
        "calmar": _round(calmar_ratio(annualized, drawdown)),
    }


def compare_benchmarks(
    frame: pd.DataFrame,
    *,
    strategy_column: str,
    benchmark_columns: Mapping[str, str],
) -> dict[str, dict[str, object]]:
    strategy_returns = frame[strategy_column].fillna(0.0)
    strategy_total = compound_return(strategy_returns)
    result: dict[str, dict[str, object]] = {}
    for column, label in benchmark_columns.items():
        if column not in frame:
            continue
        benchmark_returns = frame[column].fillna(0.0)
        benchmark_metrics = metrics_for_returns(benchmark_returns)
        benchmark_total = compound_return(benchmark_returns)
        result[column] = {
            "label": label,
            "benchmark": benchmark_metrics,
            "strategy_total_return": _round(strategy_total),
            "benchmark_total_return": _round(benchmark_total),
            "excess_return": _round(strategy_total - benchmark_total),
            "hit_rate": _round(hit_rate(strategy_returns, benchmark_returns)),
        }
    return result
