from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from myinvest_strategy_index.calmar_optimizer import daily_returns, optimize_calmar
from myinvest_strategy_index.regime_allocator import ASSET_CODES, BOND_CODE, EQUITY_CODE, get_dynamic_weights
from myinvest_strategy_index.regime_backtester import build_portfolio_returns
from myinvest_strategy_index.regime_detector import detect_regime


STRATEGY_NAMES: tuple[str, ...] = ("equal_weight", "static_calmar", "regime_switching")


@dataclass(frozen=True)
class WalkForwardWindow:
    window_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_prices: pd.DataFrame
    test_prices: pd.DataFrame


@dataclass(frozen=True)
class WindowBacktest:
    metrics: dict[str, dict[str, float]]
    returns: pd.DataFrame
    equity_curves: pd.DataFrame


def walk_forward_split(
    prices: pd.DataFrame,
    *,
    train_years: int = 2,
    test_months: int = 6,
    step_months: int = 3,
    min_train_rows: int = 252,
    min_test_rows: int = 60,
) -> list[WalkForwardWindow]:
    aligned = _aligned_prices(prices)
    _validate_window_params(train_years, test_months, step_months, min_train_rows, min_test_rows)
    windows: list[WalkForwardWindow] = []
    cursor = pd.Timestamp(aligned.index[0])
    window_id = 0

    while cursor < aligned.index[-1]:
        train_start = _first_index_at_or_after(aligned.index, cursor)
        if train_start is None:
            break
        train_end_boundary = train_start + pd.DateOffset(years=train_years)
        test_start = _first_index_at_or_after(aligned.index, train_end_boundary)
        if test_start is None:
            break
        test_end_boundary = test_start + pd.DateOffset(months=test_months)

        train_prices = aligned[(aligned.index >= train_start) & (aligned.index < train_end_boundary)]
        test_prices = aligned[(aligned.index >= test_start) & (aligned.index < test_end_boundary)]
        if len(train_prices) >= min_train_rows and len(test_prices) >= min_test_rows:
            windows.append(
                WalkForwardWindow(
                    window_id=window_id,
                    train_start=pd.Timestamp(train_prices.index[0]),
                    train_end=pd.Timestamp(train_prices.index[-1]),
                    test_start=pd.Timestamp(test_prices.index[0]),
                    test_end=pd.Timestamp(test_prices.index[-1]),
                    train_prices=train_prices,
                    test_prices=test_prices,
                )
            )
            window_id += 1

        cursor = cursor + pd.DateOffset(months=step_months)

    return windows


def run_walk_forward_backtest(
    prices: pd.DataFrame,
    *,
    train_years: int = 2,
    test_months: int = 6,
    step_months: int = 3,
    cost_bps: float = 5.0,
    seed: int = 20260703,
    static_optimizer_kwargs: dict[str, object] | None = None,
) -> dict[str, object]:
    windows = walk_forward_split(
        prices,
        train_years=train_years,
        test_months=test_months,
        step_months=step_months,
    )
    if not windows:
        raise ValueError("not enough data for walk-forward validation")

    window_results: list[dict[str, object]] = []
    window_equity_curves: dict[str, pd.DataFrame] = {}
    window_returns: list[pd.DataFrame] = []

    for window in windows:
        result = _run_window_backtest(
            window,
            cost_bps=cost_bps,
            seed=seed + window.window_id,
            static_optimizer_kwargs=static_optimizer_kwargs,
        )
        label = f"window_{window.window_id:03d}"
        window_equity_curves[label] = result.equity_curves
        window_returns.append(result.returns)
        window_results.append(
            {
                "window_id": window.window_id,
                "train_start": window.train_start.date().isoformat(),
                "train_end": window.train_end.date().isoformat(),
                "test_start": window.test_start.date().isoformat(),
                "test_end": window.test_end.date().isoformat(),
                "metrics": result.metrics,
            }
        )

    aggregate_returns = _aggregate_returns(window_returns)
    aggregate_equity = (1.0 + aggregate_returns).cumprod()
    return {
        "window_metrics": window_results,
        "mean_metrics": _aggregate_metric_frame(window_results, "mean"),
        "std_metrics": _aggregate_metric_frame(window_results, "std"),
        "worst_case_metrics": _worst_case_metrics(window_results),
        "window_equity_curves": window_equity_curves,
        "aggregated_equity_curve": aggregate_equity,
        "aggregated_returns": aggregate_returns,
    }


def _run_window_backtest(
    window: WalkForwardWindow,
    *,
    cost_bps: float,
    seed: int,
    static_optimizer_kwargs: dict[str, object] | None,
) -> WindowBacktest:
    equal_returns = _equal_weight_returns(window.test_prices)
    static_returns = _static_calmar_oos_returns(
        window.train_prices,
        window.test_prices,
        seed=seed,
        static_optimizer_kwargs=static_optimizer_kwargs,
    )
    regime_returns, regime_turnover = _regime_oos_returns(
        window.train_prices,
        window.test_prices,
        cost_bps=cost_bps,
    )
    returns = pd.concat(
        [
            equal_returns.rename("equal_weight"),
            static_returns.rename("static_calmar"),
            regime_returns.rename("regime_switching"),
        ],
        axis=1,
        join="inner",
    )
    metrics = {
        "equal_weight": _metrics_from_returns(returns["equal_weight"], turnover=0.0),
        "static_calmar": _metrics_from_returns(returns["static_calmar"], turnover=0.0),
        "regime_switching": _metrics_from_returns(returns["regime_switching"], turnover=regime_turnover),
    }
    equity_curves = (1.0 + returns).cumprod()
    return WindowBacktest(
        metrics={name: asdict(item) for name, item in metrics.items()},
        returns=returns,
        equity_curves=equity_curves,
    )


def _equal_weight_returns(prices: pd.DataFrame) -> pd.Series:
    weights = pd.Series(1.0 / len(ASSET_CODES), index=ASSET_CODES)
    return build_portfolio_returns(prices, weights).rename("equal_weight")


def _static_calmar_oos_returns(
    train_prices: pd.DataFrame,
    test_prices: pd.DataFrame,
    *,
    seed: int,
    static_optimizer_kwargs: dict[str, object] | None,
) -> pd.Series:
    optimizer_kwargs = dict(static_optimizer_kwargs or {})
    optimizer_kwargs.setdefault("seed", seed)
    train_returns = daily_returns(train_prices)
    result = optimize_calmar(train_returns, **optimizer_kwargs)
    weights = pd.Series(result.weights, index=train_prices.columns)
    return build_portfolio_returns(test_prices, weights).rename("static_calmar")


def _regime_oos_returns(
    train_prices: pd.DataFrame,
    test_prices: pd.DataFrame,
    *,
    cost_bps: float,
) -> tuple[pd.Series, float]:
    combined_prices = pd.concat([train_prices, test_prices]).sort_index()
    regime = detect_regime(combined_prices, equity_code=EQUITY_CODE, bond_code=BOND_CODE)
    weights = get_dynamic_weights(regime)
    test_weights = weights.reindex(test_prices.index).ffill().bfill()
    returns = build_portfolio_returns(test_prices, test_weights, cost_bps=cost_bps).rename("regime_switching")
    turnover = float(test_weights.diff().abs().sum(axis=1).reindex(returns.index).fillna(0.0).sum())
    return returns, turnover


def _aggregate_returns(window_returns: list[pd.DataFrame]) -> pd.DataFrame:
    combined = pd.concat(window_returns).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    return combined.loc[:, list(STRATEGY_NAMES)]


def _aggregate_metric_frame(window_results: list[dict[str, object]], method: str) -> dict[str, dict[str, float]]:
    aggregated: dict[str, dict[str, float]] = {}
    for strategy in STRATEGY_NAMES:
        frame = pd.DataFrame([item["metrics"][strategy] for item in window_results])
        frame = frame.replace([np.inf, -np.inf], np.nan)
        if method == "mean":
            values = frame.mean().fillna(0.0)
        elif method == "std":
            values = frame.std(ddof=0).fillna(0.0)
        else:
            raise ValueError(f"unsupported aggregate method: {method}")
        aggregated[strategy] = {key: float(value) for key, value in values.items()}
    return aggregated


def _worst_case_metrics(window_results: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    worst: dict[str, dict[str, float]] = {}
    for strategy in STRATEGY_NAMES:
        metrics = [item["metrics"][strategy] for item in window_results]
        worst[strategy] = min(metrics, key=lambda item: item["calmar_ratio"])
    return worst


def _metrics_from_returns(returns: pd.Series, *, turnover: float) -> "_WindowMetrics":
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
    return _WindowMetrics(cagr, volatility, sharpe, max_drawdown, calmar, float(turnover))


@dataclass(frozen=True)
class _WindowMetrics:
    cagr: float
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    calmar_ratio: float
    turnover: float


def _aligned_prices(prices: pd.DataFrame) -> pd.DataFrame:
    missing = [code for code in ASSET_CODES if code not in prices.columns]
    if missing:
        raise KeyError(f"prices missing required columns: {', '.join(missing)}")
    aligned = prices.loc[:, list(ASSET_CODES)].sort_index()
    aligned = aligned.apply(pd.to_numeric, errors="coerce").dropna(how="any")
    if len(aligned) < 2:
        raise ValueError("prices must contain at least two aligned rows")
    return aligned


def _first_index_at_or_after(index: pd.Index, target: pd.Timestamp) -> pd.Timestamp | None:
    later = index[index >= target]
    if len(later) == 0:
        return None
    return pd.Timestamp(later[0])


def _validate_window_params(
    train_years: int,
    test_months: int,
    step_months: int,
    min_train_rows: int,
    min_test_rows: int,
) -> None:
    if train_years < 1:
        raise ValueError("train_years must be positive")
    if test_months < 1:
        raise ValueError("test_months must be positive")
    if step_months < 1:
        raise ValueError("step_months must be positive")
    if min_train_rows < 2:
        raise ValueError("min_train_rows must be at least 2")
    if min_test_rows < 2:
        raise ValueError("min_test_rows must be at least 2")
