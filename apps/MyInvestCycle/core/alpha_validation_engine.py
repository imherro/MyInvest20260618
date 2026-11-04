from __future__ import annotations

from typing import Iterable

import pandas as pd


TRADING_DAYS = 252


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return round(float(drawdown.min()), 6)


def compound_return(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    return float((1.0 + returns.fillna(0.0)).prod() - 1.0)


def annualized_return(total_return: float, sessions: int) -> float | None:
    if sessions <= 0:
        return None
    return (1.0 + total_return) ** (TRADING_DAYS / sessions) - 1.0


def annualized_volatility(returns: pd.Series) -> float | None:
    clean = returns.dropna()
    if len(clean) < 2:
        return None
    return float(clean.std() * (TRADING_DAYS ** 0.5))


def sharpe_ratio(returns: pd.Series) -> float | None:
    clean = returns.dropna()
    if len(clean) < 2:
        return None
    volatility = clean.std()
    if volatility == 0:
        return None
    return float((clean.mean() / volatility) * (TRADING_DAYS ** 0.5))


def hit_rate(returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if aligned.empty:
        return None
    return float((aligned.iloc[:, 0] > aligned.iloc[:, 1]).mean())


def performance_metrics(
    returns: pd.Series,
    *,
    benchmark_returns: pd.Series | None = None,
    turnover: pd.Series | None = None,
) -> dict[str, object]:
    clean = returns.fillna(0.0)
    equity = (1.0 + clean).cumprod()
    total = compound_return(clean)
    metrics = {
        "sessions": int(len(clean)),
        "total_return": _round(total),
        "annualized_return": _round(annualized_return(total, len(clean))),
        "annualized_volatility": _round(annualized_volatility(clean)),
        "sharpe": _round(sharpe_ratio(clean)),
        "max_drawdown": max_drawdown(equity),
    }
    if benchmark_returns is not None:
        metrics["hit_rate"] = _round(hit_rate(clean, benchmark_returns.fillna(0.0)))
        metrics["excess_return"] = _round(compound_return(clean) - compound_return(benchmark_returns.fillna(0.0)))
    if turnover is not None and not turnover.empty:
        metrics["average_turnover"] = _round(float(turnover.fillna(0.0).mean()))
        metrics["cumulative_turnover"] = _round(float(turnover.fillna(0.0).sum()))
    return metrics


def benchmark_comparison(
    frame: pd.DataFrame,
    *,
    rotation_column: str = "rotation_return",
    benchmark_columns: Iterable[str],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    rotation_returns = frame[rotation_column].fillna(0.0)
    for column in benchmark_columns:
        if column not in frame:
            continue
        result[column] = performance_metrics(
            rotation_returns,
            benchmark_returns=frame[column].fillna(0.0),
            turnover=frame.get("turnover"),
        )
        result[column]["benchmark_total_return"] = _round(compound_return(frame[column].fillna(0.0)))
    return result


def regime_breakdown(
    frame: pd.DataFrame,
    *,
    regime_column: str = "regime",
    rotation_column: str = "rotation_return",
    benchmark_column: str = "benchmark_510500_return",
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for regime, group in frame.groupby(regime_column):
        rotation_total = compound_return(group[rotation_column].fillna(0.0))
        benchmark_total = compound_return(group[benchmark_column].fillna(0.0))
        result[str(regime)] = {
            "sessions": int(len(group)),
            "rotation_return": _round(rotation_total),
            "benchmark_return": _round(benchmark_total),
            "alpha": _round(rotation_total - benchmark_total),
            "hit_rate": _round(hit_rate(group[rotation_column].fillna(0.0), group[benchmark_column].fillna(0.0))),
            "average_turnover": _round(float(group.get("turnover", pd.Series(dtype=float)).fillna(0.0).mean())),
        }
    return result
