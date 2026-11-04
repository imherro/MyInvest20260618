"""TASK 4 orchestration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR
from tenbagger.portfolio import (
    BacktestConfig,
    BenchmarkLoader,
    PortfolioBuilder,
    RiskMetrics,
    load_local_task_data,
)
from tenbagger.universe import UniverseManager


def run_task4(
    universe_level: str = "dev",
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
    top_k: int = 20,
    weight_mode: str = "score",
) -> dict[str, Any]:
    universe = UniverseManager().resolve(universe_level)
    data_path = Path(data_dir)
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)

    factors, prices = load_local_task_data(data_path, universe=universe.codes)
    config = BacktestConfig(top_k=top_k, weight_mode=weight_mode)  # type: ignore[arg-type]
    builder = PortfolioBuilder(config)
    result = builder.run_backtest(factors, prices)

    backtest_dir = data_path / "backtest"
    backtest_dir.mkdir(parents=True, exist_ok=True)
    result["nav"].to_parquet(backtest_dir / "portfolio_nav.parquet", index=False)
    result["holdings"].to_parquet(backtest_dir / "portfolio_holdings.parquet", index=False)
    result["factor_contribution"].to_parquet(backtest_dir / "factor_contribution.parquet", index=False)

    returns_for_fallback = builder._prepare_inputs(factors, prices)[["date", "daily_return"]]
    benchmarks = BenchmarkLoader().load(
        result["nav"]["date"].min(),
        result["nav"]["date"].max(),
        returns_for_fallback,
    )
    metrics = RiskMetrics(config.annualization_days).summarize(result["nav"], benchmarks)

    contribution = result["factor_contribution"].copy()
    contribution["date"] = contribution["date"].astype(str)
    contribution_summary = _contribution_summary(contribution)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK 4 - Portfolio Simulation Engine",
        "universe": universe.to_api(),
        "model_provenance": {
            "model_version": "v1",
            "score_column": "tenbagger_score",
            "note": "Legacy portfolio backtest uses the V1 score column.",
        },
        "config": {
            "top_k": config.top_k,
            "rebalance": config.rebalance,
            "weight_mode": config.weight_mode,
            "transaction_cost_rate": config.transaction_cost_rate,
            "slippage_rate": config.slippage_rate,
            "apply_hard_filter": config.apply_hard_filter,
        },
        "date_range": {
            "start": str(result["nav"]["date"].min().date()),
            "end": str(result["nav"]["date"].max().date()),
        },
        "nav_rows": int(len(result["nav"])),
        "rebalance_count": int(result["holdings"]["rebalance_date"].nunique()),
        "final_nav": float(result["nav"]["nav"].iloc[-1]),
        "metrics": metrics,
        "factor_attribution": contribution_summary,
        "latest_holdings": _latest_holdings(result["holdings"]),
        "storage": {
            "portfolio_nav": str(backtest_dir / "portfolio_nav.parquet"),
            "portfolio_holdings": str(backtest_dir / "portfolio_holdings.parquet"),
            "factor_contribution": str(backtest_dir / "factor_contribution.parquet"),
        },
    }

    (report_path / "task4_backtest_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown(report, report_path / "task4_backtest_summary.md")
    return report


def _contribution_summary(contribution: pd.DataFrame) -> dict[str, Any]:
    columns = [column for column in contribution.columns if column.endswith("_contribution")]
    means = {column: float(contribution[column].mean()) for column in columns}
    dominant = max(means, key=means.get) if means else ""
    return {
        "dominant_factor": dominant.replace("_contribution", ""),
        "mean_contribution": means,
        "rolling_contribution": contribution.tail(12).to_dict(orient="records"),
    }


def _latest_holdings(holdings: pd.DataFrame) -> list[dict[str, Any]]:
    if holdings.empty:
        return []
    latest = holdings[holdings["rebalance_date"] == holdings["rebalance_date"].max()].copy()
    latest["rebalance_date"] = latest["rebalance_date"].astype(str)
    return latest.sort_values("weight", ascending=False).to_dict(orient="records")


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    metrics = report["metrics"]
    lines = [
        "# TASK 4 Backtest Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Date range: {report['date_range']['start']} to {report['date_range']['end']}",
        f"- NAV rows: {report['nav_rows']}",
        f"- Rebalance count: {report['rebalance_count']}",
        f"- Final NAV: {report['final_nav']:.4f}",
        f"- Annual return: {metrics['annual_return']:.4f}",
        f"- Sharpe: {metrics['sharpe']:.4f}",
        f"- Max drawdown: {metrics['max_drawdown']:.4f}",
        f"- Volatility: {metrics['volatility']:.4f}",
        f"- Win rate: {metrics['win_rate']:.4f}",
        f"- Turnover rate: {metrics['turnover_rate']:.4f}",
        f"- Total transaction cost: {metrics['total_transaction_cost']:.4f}",
        "",
        "## Benchmarks",
        "",
    ]
    for name, benchmark in metrics.get("benchmarks", {}).items():
        lines.append(
            f"- {name}: annual_return={benchmark['annual_return']:.4f}, excess={benchmark['excess_return']:.4f}, beta={benchmark['beta']:.4f}, max_drawdown={benchmark['max_drawdown']:.4f}"
        )
    lines.extend(["", "## Factor Attribution", ""])
    lines.append(f"- Dominant factor: {report['factor_attribution']['dominant_factor']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
