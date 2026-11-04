from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from myinvest_strategy_index.config import Settings, load_settings


ASSETS: tuple[tuple[str, str], ...] = (
    ("h21052.CSI", "国信价值全收益指数"),
    ("CN2296.CNI", "创成长R收益指数"),
    ("h20269.CSI", "红利低波全收益指数"),
    ("480092.CNI", "自由现金流R收益指数"),
    ("518880.SH", "518880 华安黄金ETF"),
    ("511260.SH", "511260 十年国债ETF"),
)


@dataclass(frozen=True)
class PortfolioMetrics:
    cagr: float
    volatility: float
    max_drawdown: float
    sharpe: float
    calmar: float


@dataclass(frozen=True)
class OptimizationResult:
    weights: np.ndarray
    metrics: PortfolioMetrics
    seed: int
    candidates: int


def load_price_frame(settings: Settings, asset_codes: tuple[str, ...] | None = None) -> pd.DataFrame:
    codes = asset_codes or tuple(code for code, _ in ASSETS)
    frames: list[pd.Series] = []
    for code in codes:
        path = settings.cache_dir / f"value_compare_{code.replace('.', '_')}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing cached price file: {path}")
        frame = pd.read_csv(path, parse_dates=["date"])
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        series = (
            frame.dropna(subset=["date", "value"])
            .sort_values("date")
            .drop_duplicates("date", keep="last")
            .set_index("date")["value"]
            .rename(code)
        )
        if series.empty:
            raise RuntimeError(f"Cached price file has no usable rows: {path}")
        frames.append(series)
    prices = pd.concat(frames, axis=1, join="inner").dropna()
    if len(prices) < 252:
        raise RuntimeError("Aligned sample is too short for portfolio optimization")
    return prices


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change().dropna(how="any")
    if returns.empty:
        raise RuntimeError("No usable returns after price alignment")
    return returns


def evaluate_portfolio(returns: pd.DataFrame, weights: np.ndarray) -> PortfolioMetrics:
    portfolio_returns = returns.to_numpy(dtype=float) @ weights
    return _metrics_from_returns(portfolio_returns, returns.index)


def equity_curve(returns: pd.DataFrame, weights: np.ndarray, name: str) -> pd.Series:
    portfolio_returns = returns.to_numpy(dtype=float) @ weights
    values = np.cumprod(1.0 + portfolio_returns)
    return pd.Series(values, index=returns.index, name=name)


def optimize_calmar(
    returns: pd.DataFrame,
    *,
    seed: int = 20260703,
    max_weight: float = 0.40,
    random_candidates: int = 120_000,
    local_rounds: int = 6,
    local_candidates: int = 8_000,
    batch_size: int = 4_000,
) -> OptimizationResult:
    if max_weight * returns.shape[1] < 1.0:
        raise ValueError("max_weight is too low for the number of assets")

    rng = np.random.default_rng(seed)
    returns_array = returns.to_numpy(dtype=float)
    dates = returns.index
    best_weights: np.ndarray | None = None
    best_metrics: PortfolioMetrics | None = None
    evaluated = 0

    base_candidates = np.vstack(
        [
            np.full(returns.shape[1], 1.0 / returns.shape[1]),
            _project_to_capped_simplex(np.arange(1, returns.shape[1] + 1, dtype=float), max_weight),
        ]
    )
    best_weights, best_metrics, count = _best_candidate(returns_array, dates, base_candidates)
    evaluated += count

    remaining = random_candidates
    while remaining > 0:
        count = min(batch_size, remaining)
        candidates = _random_feasible_weights(rng, count, returns.shape[1], max_weight)
        weights, metrics, evaluated_count = _best_candidate(returns_array, dates, candidates)
        evaluated += evaluated_count
        if metrics.calmar > best_metrics.calmar:
            best_weights, best_metrics = weights, metrics
        remaining -= count

    for scale in np.geomspace(0.12, 0.01, local_rounds):
        remaining = local_candidates
        while remaining > 0:
            count = min(batch_size, remaining)
            noise = rng.normal(0.0, scale, size=(count, returns.shape[1]))
            candidates = np.vstack(
                [_project_to_capped_simplex(best_weights + row, max_weight) for row in noise]
            )
            weights, metrics, evaluated_count = _best_candidate(returns_array, dates, candidates)
            evaluated += evaluated_count
            if metrics.calmar > best_metrics.calmar:
                best_weights, best_metrics = weights, metrics
            remaining -= count

    return OptimizationResult(best_weights, best_metrics, seed, evaluated)


def write_report(
    settings: Settings,
    *,
    seed: int = 20260703,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    prices = load_price_frame(settings)
    returns = daily_returns(prices)
    split_index = int(len(returns) * 0.70)
    train_returns = returns.iloc[:split_index]
    test_returns = returns.iloc[split_index:]

    full_result = optimize_calmar(returns, seed=seed)
    train_result = optimize_calmar(train_returns, seed=seed + 1)
    equal_weights = np.full(len(ASSETS), 1.0 / len(ASSETS))

    output_base = output_dir or settings.root / "reports" / "calmar_optimizer"
    output_base.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    stem = f"calmar_optimization_{timestamp}"
    report_path = output_base / f"{stem}.md"
    weights_path = output_base / f"{stem}_weights.csv"
    equity_path = output_base / f"{stem}_equity.csv"
    plot_path = output_base / f"{stem}_equity.png"

    metrics_rows = [
        _metrics_row("Full optimized", evaluate_portfolio(returns, full_result.weights)),
        _metrics_row("Full equal weight", evaluate_portfolio(returns, equal_weights)),
        _metrics_row("Train optimized", evaluate_portfolio(train_returns, train_result.weights)),
        _metrics_row("Train equal weight", evaluate_portfolio(train_returns, equal_weights)),
        _metrics_row("OOS train-opt frozen", evaluate_portfolio(test_returns, train_result.weights)),
        _metrics_row("OOS equal weight", evaluate_portfolio(test_returns, equal_weights)),
    ]
    metrics_frame = pd.DataFrame(metrics_rows)

    weights_frame = pd.DataFrame(
        {
            "code": [code for code, _ in ASSETS],
            "name": [name for _, name in ASSETS],
            "full_sample_opt_weight": full_result.weights,
            "train_70pct_opt_weight": train_result.weights,
            "equal_weight": equal_weights,
        }
    )
    weights_frame.to_csv(weights_path, index=False, encoding="utf-8-sig")

    equity = pd.concat(
        [
            equity_curve(returns, full_result.weights, "full_optimized"),
            equity_curve(returns, equal_weights, "equal_weight"),
            equity_curve(returns, train_result.weights, "train_optimized_frozen"),
        ],
        axis=1,
    )
    equity.to_csv(equity_path, index_label="date", encoding="utf-8-sig")
    _plot_equity(equity, split_date=test_returns.index[0], path=plot_path)

    report_path.write_text(
        _render_markdown_report(
            prices=prices,
            returns=returns,
            train_returns=train_returns,
            test_returns=test_returns,
            full_result=full_result,
            train_result=train_result,
            weights_frame=weights_frame,
            metrics_frame=metrics_frame,
            weights_path=weights_path,
            equity_path=equity_path,
            plot_path=plot_path,
            root=settings.root,
        ),
        encoding="utf-8",
    )
    return {
        "report": report_path,
        "weights": weights_path,
        "equity": equity_path,
        "plot": plot_path,
    }


def _metrics_from_returns(portfolio_returns: np.ndarray, dates: pd.Index) -> PortfolioMetrics:
    portfolio_returns = np.asarray(portfolio_returns, dtype=float)
    equity = np.cumprod(1.0 + portfolio_returns)
    days = max((pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days, 1)
    total = float(equity[-1])
    cagr = total ** (365.25 / days) - 1.0
    volatility = float(np.std(portfolio_returns, ddof=1) * math.sqrt(252))
    mean_return = float(np.mean(portfolio_returns))
    std_return = float(np.std(portfolio_returns, ddof=1))
    sharpe = mean_return / std_return * math.sqrt(252) if std_return > 0 else math.nan
    running_max = np.maximum.accumulate(np.insert(equity, 0, 1.0))
    drawdown = np.insert(equity, 0, 1.0) / running_max - 1.0
    max_drawdown = abs(float(np.min(drawdown)))
    calmar = cagr / max_drawdown if max_drawdown > 0 else math.inf
    return PortfolioMetrics(cagr, volatility, max_drawdown, sharpe, calmar)


def _best_candidate(
    returns: np.ndarray, dates: pd.Index, candidates: np.ndarray
) -> tuple[np.ndarray, PortfolioMetrics, int]:
    portfolio_returns = returns @ candidates.T
    equity = np.cumprod(1.0 + portfolio_returns, axis=0)
    days = max((pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days, 1)
    cagr = np.power(equity[-1], 365.25 / days) - 1.0
    volatility = np.std(portfolio_returns, axis=0, ddof=1) * math.sqrt(252)
    mean_return = np.mean(portfolio_returns, axis=0)
    std_return = np.std(portfolio_returns, axis=0, ddof=1)
    sharpe = np.divide(
        mean_return * math.sqrt(252),
        std_return,
        out=np.full_like(mean_return, np.nan),
        where=std_return > 0,
    )
    equity_with_start = np.vstack([np.ones(candidates.shape[0]), equity])
    running_max = np.maximum.accumulate(equity_with_start, axis=0)
    drawdown = equity_with_start / running_max - 1.0
    max_drawdown = np.abs(np.min(drawdown, axis=0))
    calmar = np.divide(
        cagr,
        max_drawdown,
        out=np.full_like(cagr, -np.inf),
        where=max_drawdown > 0,
    )
    best_index = int(np.argmax(calmar))
    metrics = PortfolioMetrics(
        cagr=float(cagr[best_index]),
        volatility=float(volatility[best_index]),
        max_drawdown=float(max_drawdown[best_index]),
        sharpe=float(sharpe[best_index]),
        calmar=float(calmar[best_index]),
    )
    return candidates[best_index].copy(), metrics, len(candidates)


def _random_feasible_weights(
    rng: np.random.Generator, count: int, n_assets: int, max_weight: float
) -> np.ndarray:
    accepted: list[np.ndarray] = []
    while sum(len(batch) for batch in accepted) < count:
        batch = rng.dirichlet(np.ones(n_assets), size=max(count * 2, 1_000))
        batch = batch[np.all(batch <= max_weight + 1e-12, axis=1)]
        if len(batch):
            accepted.append(batch)
    return np.vstack(accepted)[:count]


def _project_to_capped_simplex(values: np.ndarray, max_weight: float) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if len(values) * max_weight < 1.0:
        raise ValueError("max_weight is too low for the number of assets")
    low = float(np.min(values) - max_weight)
    high = float(np.max(values))
    for _ in range(80):
        tau = (low + high) / 2.0
        weights = np.clip(values - tau, 0.0, max_weight)
        if weights.sum() > 1.0:
            low = tau
        else:
            high = tau
    weights = np.clip(values - high, 0.0, max_weight)
    return weights / weights.sum()


def _metrics_row(label: str, metrics: PortfolioMetrics) -> dict[str, object]:
    return {
        "portfolio": label,
        "CAGR": metrics.cagr,
        "Volatility": metrics.volatility,
        "MaxDrawdown": metrics.max_drawdown,
        "Sharpe": metrics.sharpe,
        "Calmar": metrics.calmar,
    }


def _pct(value: float) -> str:
    return f"{value:.2%}"


def _num(value: float) -> str:
    return f"{value:.3f}"


def _render_markdown_table(frame: pd.DataFrame, percent_columns: set[str]) -> str:
    headers = list(frame.columns)
    rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in frame.iterrows():
        cells: list[str] = []
        for header in headers:
            value = row[header]
            if header in percent_columns:
                cells.append(_pct(float(value)))
            elif isinstance(value, float):
                cells.append(_num(value))
            else:
                cells.append(str(value))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _render_markdown_report(
    *,
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    train_returns: pd.DataFrame,
    test_returns: pd.DataFrame,
    full_result: OptimizationResult,
    train_result: OptimizationResult,
    weights_frame: pd.DataFrame,
    metrics_frame: pd.DataFrame,
    weights_path: Path,
    equity_path: Path,
    plot_path: Path,
    root: Path,
) -> str:
    weights_table = weights_frame.copy()
    metrics_table = metrics_frame.copy()
    weights_display = _display_path(weights_path, root)
    equity_display = _display_path(equity_path, root)
    plot_display = _display_path(plot_path, root)
    return "\n".join(
        [
            "# Calmar Ratio Portfolio Optimization",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Assets: {len(ASSETS)}",
            f"Aligned price sample: {prices.index[0].date()} to {prices.index[-1].date()} ({len(prices)} rows)",
            f"Return sample: {returns.index[0].date()} to {returns.index[-1].date()} ({len(returns)} rows)",
            f"Train/OOS split: train {train_returns.index[0].date()} to {train_returns.index[-1].date()} ({len(train_returns)} rows); OOS {test_returns.index[0].date()} to {test_returns.index[-1].date()} ({len(test_returns)} rows)",
            "",
            "## Method",
            "",
            "- Objective: maximize Calmar Ratio = CAGR / MaxDrawdown.",
            "- Constraints: long-only, weights sum to 1, each weight between 0 and 40%.",
            f"- Optimization: reproducible random search plus capped-simplex local refinement. Full-sample seed `{full_result.seed}`, train seed `{train_result.seed}`.",
            f"- Evaluated candidates: full sample {full_result.candidates:,}; train sample {train_result.candidates:,}.",
            "",
            "## Optimal Weights",
            "",
            _render_markdown_table(
                weights_table,
                {"full_sample_opt_weight", "train_70pct_opt_weight", "equal_weight"},
            ),
            "",
            "## Metrics",
            "",
            _render_markdown_table(
                metrics_table,
                {"CAGR", "Volatility", "MaxDrawdown"},
            ),
            "",
            "## Output Files",
            "",
            f"- Weights CSV: `{weights_display}`",
            f"- Equity CSV: `{equity_display}`",
            f"- Equity plot: `{plot_display}`",
            "",
            "## Notes",
            "",
            "- Full-sample optimal weights are optimized on the entire aligned history and are not an out-of-sample claim.",
            "- OOS train-opt frozen uses only the first 70% of returns to choose weights, then holds those weights fixed for the last 30%.",
            "- Equal weight is 1/6 per asset.",
            "",
        ]
    )


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _plot_equity(equity: pd.DataFrame, *, split_date: pd.Timestamp, path: Path) -> None:
    import matplotlib.pyplot as plt

    plt.figure(figsize=(11, 6))
    for column in equity.columns:
        plt.plot(equity.index, equity[column], label=column)
    plt.axvline(split_date, color="#666666", linestyle="--", linewidth=1, label="70/30 split")
    plt.title("Calmar Optimization Equity Curves")
    plt.xlabel("Date")
    plt.ylabel("Equity")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optimize six-asset portfolio weights for Calmar Ratio")
    parser.add_argument("--seed", type=int, default=20260703)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    paths = write_report(load_settings(), seed=args.seed, output_dir=args.output_dir)
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
