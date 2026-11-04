from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from myinvest_strategy_index.calmar_optimizer import daily_returns, optimize_calmar
from myinvest_strategy_index.regime_allocator import (
    ASSET_CODES,
    BOND_CODE,
    EQUITY_CODE,
    get_dynamic_weights,
)
from myinvest_strategy_index.regime_detector import detect_regime


@dataclass(frozen=True)
class BacktestMetrics:
    cagr: float
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    calmar_ratio: float
    turnover: float


@dataclass(frozen=True)
class StrategyBacktest:
    name: str
    returns: pd.Series
    equity_curve: pd.Series
    drawdown_curve: pd.Series
    metrics: BacktestMetrics
    weights: pd.DataFrame


def build_portfolio_returns(
    prices: pd.DataFrame,
    weights: pd.DataFrame | pd.Series | np.ndarray,
    *,
    cost_bps: float = 0.0,
) -> pd.Series:
    """Build portfolio returns from prices and static or dynamic target weights."""
    aligned_prices = _aligned_prices(prices)
    returns = daily_returns(aligned_prices)
    target_weights = _target_weight_frame(weights, aligned_prices)
    held_weights = target_weights.shift(1).reindex(returns.index)
    held_weights.iloc[0] = target_weights.iloc[0]
    held_weights = held_weights.ffill()

    portfolio_returns = (returns * held_weights).sum(axis=1)
    if cost_bps:
        turnover = _turnover_series(target_weights).reindex(returns.index).fillna(0.0)
        portfolio_returns = portfolio_returns - turnover * (float(cost_bps) / 10_000.0)
    return portfolio_returns.rename("portfolio_return")


def backtest_equal_weight(prices: pd.DataFrame) -> StrategyBacktest:
    aligned_prices = _aligned_prices(prices)
    weights = pd.Series(1.0 / len(aligned_prices.columns), index=aligned_prices.columns)
    returns = build_portfolio_returns(aligned_prices, weights)
    return _strategy_backtest("equal_weight", returns, _target_weight_frame(weights, aligned_prices))


def backtest_static_calmar(
    prices: pd.DataFrame,
    *,
    seed: int = 20260703,
    max_weight: float = 0.40,
    random_candidates: int = 120_000,
    local_rounds: int = 6,
    local_candidates: int = 8_000,
    batch_size: int = 4_000,
) -> StrategyBacktest:
    aligned_prices = _aligned_prices(prices)
    returns = daily_returns(aligned_prices)
    result = optimize_calmar(
        returns,
        seed=seed,
        max_weight=max_weight,
        random_candidates=random_candidates,
        local_rounds=local_rounds,
        local_candidates=local_candidates,
        batch_size=batch_size,
    )
    weights = pd.Series(result.weights, index=aligned_prices.columns)
    portfolio_returns = build_portfolio_returns(aligned_prices, weights)
    return _strategy_backtest("static_calmar", portfolio_returns, _target_weight_frame(weights, aligned_prices))


def backtest_regime_strategy(
    prices: pd.DataFrame,
    *,
    cost_bps: float = 5.0,
) -> StrategyBacktest:
    aligned_prices = _aligned_prices(prices)
    regime = detect_regime(aligned_prices, equity_code=EQUITY_CODE, bond_code=BOND_CODE)
    weights = get_dynamic_weights(regime).reindex(aligned_prices.index).ffill().bfill()
    returns = build_portfolio_returns(aligned_prices, weights, cost_bps=cost_bps)
    return _strategy_backtest("regime_switching", returns, weights)


def run_backtest_comparison(
    prices: pd.DataFrame,
    *,
    cost_bps: float = 5.0,
    seed: int = 20260703,
    static_optimizer_kwargs: dict[str, object] | None = None,
) -> dict[str, object]:
    static_kwargs = dict(static_optimizer_kwargs or {})
    static_kwargs.setdefault("seed", seed)
    strategies = (
        backtest_equal_weight(prices),
        backtest_static_calmar(prices, **static_kwargs),
        backtest_regime_strategy(prices, cost_bps=cost_bps),
    )
    equity_curves = pd.concat([item.equity_curve for item in strategies], axis=1, join="inner")
    drawdown_curves = pd.concat([item.drawdown_curve for item in strategies], axis=1, join="inner")
    return {
        "metrics": {item.name: asdict(item.metrics) for item in strategies},
        "equity_curves": equity_curves,
        "drawdown_curves": drawdown_curves,
        "returns": pd.concat([item.returns.rename(item.name) for item in strategies], axis=1, join="inner"),
        "weights": {item.name: item.weights for item in strategies},
    }


def _aligned_prices(prices: pd.DataFrame) -> pd.DataFrame:
    missing = [code for code in ASSET_CODES if code not in prices.columns]
    if missing:
        raise KeyError(f"prices missing required columns: {', '.join(missing)}")
    aligned = prices.loc[:, list(ASSET_CODES)].sort_index()
    aligned = aligned.apply(pd.to_numeric, errors="coerce").dropna(how="any")
    if len(aligned) < 2:
        raise ValueError("prices must contain at least two aligned rows")
    return aligned


def _target_weight_frame(
    weights: pd.DataFrame | pd.Series | np.ndarray,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    if isinstance(weights, pd.DataFrame):
        missing = [code for code in prices.columns if code not in weights.columns]
        if missing:
            raise KeyError(f"weights missing required columns: {', '.join(missing)}")
        frame = weights.loc[:, prices.columns].reindex(prices.index).ffill().bfill()
    else:
        series = pd.Series(np.asarray(weights, dtype=float), index=prices.columns) if not isinstance(weights, pd.Series) else weights
        missing = [code for code in prices.columns if code not in series.index]
        if missing:
            raise KeyError(f"weights missing required columns: {', '.join(missing)}")
        series = series.loc[prices.columns].astype(float)
        frame = pd.DataFrame(np.tile(series.to_numpy(), (len(prices), 1)), index=prices.index, columns=prices.columns)
    _validate_weight_frame(frame)
    return frame


def _validate_weight_frame(weights: pd.DataFrame) -> None:
    if weights.isna().any().any():
        raise ValueError("weights contain NaN")
    if (weights < -1e-12).any().any():
        raise ValueError("weights must be long-only")
    sums = weights.sum(axis=1)
    if not (sums.sub(1.0).abs() <= 1e-10).all():
        raise ValueError("weights must sum to 1")


def _turnover_series(weights: pd.DataFrame) -> pd.Series:
    return weights.diff().abs().sum(axis=1).fillna(0.0).rename("turnover")


def _strategy_backtest(name: str, returns: pd.Series, weights: pd.DataFrame) -> StrategyBacktest:
    equity = (1.0 + returns).cumprod().rename(name)
    drawdown = (equity / equity.cummax() - 1.0).rename(name)
    turnover = float(_turnover_series(weights).reindex(returns.index).fillna(0.0).sum())
    metrics = _metrics_from_returns(returns, turnover=turnover)
    return StrategyBacktest(name, returns.rename(name), equity, drawdown, metrics, weights)


def _metrics_from_returns(returns: pd.Series, *, turnover: float) -> BacktestMetrics:
    if returns.empty:
        raise ValueError("returns must not be empty")
    equity = (1.0 + returns).cumprod()
    days = max((pd.Timestamp(returns.index[-1]) - pd.Timestamp(returns.index[0])).days, 1)
    cagr = float(equity.iloc[-1] ** (365.25 / days) - 1.0)
    volatility = float(returns.std(ddof=1) * math.sqrt(252))
    std_return = float(returns.std(ddof=1))
    sharpe = float(returns.mean() / std_return * math.sqrt(252)) if std_return > 0 else math.nan
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = abs(float(drawdown.min()))
    calmar = cagr / max_drawdown if max_drawdown > 0 else math.inf
    return BacktestMetrics(
        cagr=cagr,
        annualized_volatility=volatility,
        sharpe_ratio=sharpe,
        max_drawdown=max_drawdown,
        calmar_ratio=calmar,
        turnover=float(turnover),
    )
