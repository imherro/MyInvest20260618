from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from tenbagger.factor_engine import FactorEngine
from tenbagger.portfolio import BacktestConfig, PortfolioBuilder, RiskMetrics


def _task_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    start = date(2024, 1, 1)
    for idx, code in enumerate(["A", "B", "C", "D", "E"]):
        for day in range(180):
            current = start + timedelta(days=day)
            if current.weekday() >= 5:
                continue
            rows.append(
                {
                    "ts_code": code,
                    "date": current.isoformat(),
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10 + idx + day * (0.02 + idx * 0.005),
                    "revenue": 100 + idx * 20 + day,
                    "net_profit": 10 + idx * 2 + day * 0.1,
                    "roe": 1 + idx,
                    "pe": 10 + idx,
                    "pb": 1 + idx * 0.1,
                    "market_cap": 100 + idx,
                    "industry": "tech" if idx < 3 else "health",
                    "ann_date": "20231231",
                    "report_period": "20231231",
                    "debt_ratio": 0.3,
                }
            )
    prices = pd.DataFrame(rows)
    factors = FactorEngine().compute(prices)
    return factors, prices


def test_portfolio_builder_produces_nav_and_holdings() -> None:
    factors, prices = _task_data()
    result = PortfolioBuilder(BacktestConfig(top_k=3)).run_backtest(factors, prices)

    assert not result["nav"].empty
    assert not result["holdings"].empty
    assert result["nav"]["nav"].iloc[-1] > 0


def test_risk_metrics_include_required_fields() -> None:
    factors, prices = _task_data()
    result = PortfolioBuilder(BacktestConfig(top_k=3)).run_backtest(factors, prices)
    benchmark = result["nav"][["date", "portfolio_return"]].rename(
        columns={"portfolio_return": "benchmark_return"}
    )
    metrics = RiskMetrics().summarize(result["nav"], {"TEST": benchmark})

    for field in ["annual_return", "sharpe", "max_drawdown", "volatility", "win_rate", "turnover_rate"]:
        assert field in metrics
    assert "TEST" in metrics["benchmarks"]
