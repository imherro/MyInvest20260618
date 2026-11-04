from __future__ import annotations

import itertools
import math
from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from myinvest_strategy_index.regime_allocator import ASSET_CODES, BOND_CODE, EQUITY_CODE, get_dynamic_weights
from myinvest_strategy_index.regime_backtester import build_portfolio_returns
from myinvest_strategy_index.regime_detector import detect_regime


DEFAULT_MOMENTUM_WINDOWS: tuple[int, ...] = (60, 90, 120, 180)
DEFAULT_VOLATILITY_WINDOWS: tuple[int, ...] = (10, 20, 30, 60)
DEFAULT_VOLATILITY_BASELINE_WINDOWS: tuple[int, ...] = (60, 120, 180)
DEFAULT_COST_BPS_VALUES: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0)

METRIC_COLUMNS: tuple[str, ...] = (
    "cagr",
    "annualized_volatility",
    "sharpe_ratio",
    "max_drawdown",
    "calmar_ratio",
    "turnover",
)


@dataclass(frozen=True)
class SensitivityMetrics:
    cagr: float
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    calmar_ratio: float
    turnover: float


def run_sensitivity_analysis(
    prices: pd.DataFrame,
    *,
    momentum_windows: Iterable[int] = DEFAULT_MOMENTUM_WINDOWS,
    volatility_windows: Iterable[int] = DEFAULT_VOLATILITY_WINDOWS,
    volatility_baseline_windows: Iterable[int] = DEFAULT_VOLATILITY_BASELINE_WINDOWS,
    cost_bps_values: Iterable[float] = DEFAULT_COST_BPS_VALUES,
) -> dict[str, object]:
    """Evaluate regime strategy robustness across detector and cost parameters."""
    aligned = _aligned_prices(prices)
    rows: list[dict[str, float]] = []
    for momentum_window, volatility_window, baseline_window, cost_bps in parameter_grid(
        momentum_windows=momentum_windows,
        volatility_windows=volatility_windows,
        volatility_baseline_windows=volatility_baseline_windows,
        cost_bps_values=cost_bps_values,
    ):
        metrics = _evaluate_parameter_set(
            aligned,
            momentum_window=momentum_window,
            volatility_window=volatility_window,
            volatility_baseline_window=baseline_window,
            cost_bps=cost_bps,
        )
        rows.append(
            {
                "momentum_window": int(momentum_window),
                "volatility_window": int(volatility_window),
                "volatility_baseline_window": int(baseline_window),
                "cost_bps": float(cost_bps),
                **asdict(metrics),
            }
        )

    matrix = pd.DataFrame(rows)
    if matrix.empty:
        raise ValueError("parameter grid must not be empty")
    matrix = matrix.set_index(
        [
            "momentum_window",
            "volatility_window",
            "volatility_baseline_window",
            "cost_bps",
        ]
    ).sort_index()
    matrix = matrix.loc[:, list(METRIC_COLUMNS)]
    stability = _stability_metrics(matrix)
    heatmap_data = matrix.reset_index()
    return {
        "sensitivity_matrix": matrix,
        "stability_metrics": stability,
        "heatmap_data": heatmap_data,
    }


def parameter_grid(
    *,
    momentum_windows: Iterable[int] = DEFAULT_MOMENTUM_WINDOWS,
    volatility_windows: Iterable[int] = DEFAULT_VOLATILITY_WINDOWS,
    volatility_baseline_windows: Iterable[int] = DEFAULT_VOLATILITY_BASELINE_WINDOWS,
    cost_bps_values: Iterable[float] = DEFAULT_COST_BPS_VALUES,
) -> list[tuple[int, int, int, float]]:
    momentum = [int(item) for item in momentum_windows]
    volatility = [int(item) for item in volatility_windows]
    baseline = [int(item) for item in volatility_baseline_windows]
    costs = [float(item) for item in cost_bps_values]
    if not momentum or not volatility or not baseline or not costs:
        raise ValueError("all parameter lists must contain at least one value")
    combos = list(itertools.product(momentum, volatility, baseline, costs))
    invalid = [(m, v, b, c) for m, v, b, c in combos if b < v]
    if invalid:
        raise ValueError("volatility_baseline_window must be >= volatility_window for all combinations")
    return combos


def _evaluate_parameter_set(
    prices: pd.DataFrame,
    *,
    momentum_window: int,
    volatility_window: int,
    volatility_baseline_window: int,
    cost_bps: float,
) -> SensitivityMetrics:
    regime = detect_regime(
        prices,
        equity_code=EQUITY_CODE,
        bond_code=BOND_CODE,
        momentum_window=momentum_window,
        volatility_window=volatility_window,
        volatility_baseline_window=volatility_baseline_window,
    )
    weights = get_dynamic_weights(regime).reindex(prices.index).ffill().bfill()
    returns = build_portfolio_returns(prices, weights, cost_bps=cost_bps)
    turnover = float(weights.diff().abs().sum(axis=1).reindex(returns.index).fillna(0.0).sum())
    return _metrics_from_returns(returns, turnover=turnover)


def _metrics_from_returns(returns: pd.Series, *, turnover: float) -> SensitivityMetrics:
    if returns.empty:
        raise ValueError("returns must not be empty")
    equity = (1.0 + returns).cumprod()
    days = max((pd.Timestamp(returns.index[-1]) - pd.Timestamp(returns.index[0])).days, 1)
    cagr = float(equity.iloc[-1] ** (365.25 / days) - 1.0)
    volatility = float(returns.std(ddof=1) * math.sqrt(252))
    std_return = float(returns.std(ddof=1))
    sharpe = float(returns.mean() / std_return * math.sqrt(252)) if std_return > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = abs(float(drawdown.min()))
    calmar = cagr / max(max_drawdown, 1e-12)
    return SensitivityMetrics(
        cagr=cagr,
        annualized_volatility=volatility,
        sharpe_ratio=sharpe,
        max_drawdown=max_drawdown,
        calmar_ratio=float(calmar),
        turnover=float(turnover),
    )


def _stability_metrics(matrix: pd.DataFrame) -> dict[str, float]:
    calmar = matrix["calmar_ratio"].replace([np.inf, -np.inf], np.nan).dropna()
    if calmar.empty:
        raise ValueError("calmar_ratio has no finite observations")
    return {
        "mean_calmar": float(calmar.mean()),
        "std_calmar": float(calmar.std(ddof=0)),
        "worst_calmar": float(calmar.min()),
        "best_calmar": float(calmar.max()),
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
