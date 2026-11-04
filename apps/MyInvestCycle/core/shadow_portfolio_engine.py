from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from config import DATA_DIR
from core.benchmark_loader import DEFAULT_BENCHMARK_CODE, benchmark_returns_frame
from core.exposure_controller import build_exposure_decision
from core.portfolio_allocator import build_portfolio_allocation
from core.regime_adapter import validate_risk_signal
from core.risk_score_engine import load_risk_policy
from core.strategy_filter import load_strategy_policy
from core.strategy_router import build_strategy_route
from core.capital_controller import load_portfolio_policy


DEFAULT_SURVIVAL_DATASET = DATA_DIR / "structural_survival_dataset.json"


def load_structural_survival_rows(path: str | Path = DEFAULT_SURVIVAL_DATASET) -> list[dict[str, object]]:
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"structural survival dataset not found: {dataset_path}")
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"structural survival dataset must be a list: {dataset_path}")
    return [row for row in payload if isinstance(row, dict)]


def _score(features: Mapping[str, object], key: str, default: float = 0.0) -> float:
    return round(float(features.get(key, default)), 6)


def risk_signal_from_survival_row(
    row: Mapping[str, object],
    *,
    regime_field: str = "raw_regime",
) -> dict[str, object]:
    features = row.get("features")
    if not isinstance(features, Mapping):
        raise ValueError(f"survival row missing features: {row!r}")

    regime = row.get(regime_field) or row.get("regime") or row.get("structural_regime")
    signal = {
        "as_of": str(row["date"]),
        "regime": str(regime),
        "confidence": _score(features, "confidence"),
        "trend": _score(features, "trend"),
        "breadth": _score(features, "breadth"),
        "liquidity": _score(features, "liquidity"),
        "volatility": _score(features, "volatility"),
        "regime_score": _score(features, "regime_score"),
    }
    validate_risk_signal(signal)
    return signal


def build_daily_shadow_decisions(
    survival_rows: list[dict[str, object]],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    regime_field: str = "raw_regime",
) -> pd.DataFrame:
    risk_policy = load_risk_policy()
    portfolio_policy = load_portfolio_policy()
    strategy_policy = load_strategy_policy()
    decisions: list[dict[str, object]] = []

    for row in sorted(survival_rows, key=lambda item: str(item.get("date", ""))):
        date_text = str(row.get("date"))
        if start_date and date_text < start_date:
            continue
        if end_date and date_text > end_date:
            continue

        signal = risk_signal_from_survival_row(row, regime_field=regime_field)
        risk_decision = build_exposure_decision(signal, policy=risk_policy)
        portfolio = build_portfolio_allocation(
            {"input": signal, "decision": risk_decision},
            policy=portfolio_policy,
        )
        strategy_route = build_strategy_route(portfolio, policy=strategy_policy)
        decisions.append(
            {
                "date": signal["as_of"],
                "regime": signal["regime"],
                "confidence": signal["confidence"],
                "risk_score": risk_decision["risk_score"],
                "risk_level": risk_decision["risk_level"],
                "r2_exposure": portfolio["total_exposure"],
                "cash_ratio": portfolio["cash_ratio"],
                "enabled_strategies": strategy_route["enabled_strategies"],
                "disabled_strategies": strategy_route["disabled_strategies"],
            }
        )

    if not decisions:
        raise ValueError("no shadow decisions generated for the requested window")
    return pd.DataFrame(decisions).sort_values("date").reset_index(drop=True)


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return round(float(drawdown.min()), 6)


def _curve_records(frame: pd.DataFrame, value_column: str) -> list[dict[str, object]]:
    return [
        {"date": str(row["date"]), "value": round(float(row[value_column]), 6)}
        for _, row in frame[["date", value_column]].iterrows()
    ]


def _return_records(frame: pd.DataFrame, value_column: str) -> list[dict[str, object]]:
    return [
        {"date": str(row["date"]), "return": round(float(row[value_column]), 8)}
        for _, row in frame[["date", value_column]].iterrows()
    ]


def _decision_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        records.append(
            {
                "date": str(row["date"]),
                "regime": str(row["regime"]),
                "risk_level": str(row["risk_level"]),
                "risk_score": round(float(row["risk_score"]), 6),
                "signal_exposure": round(float(row["r2_exposure"]), 6),
                "applied_exposure": round(float(row["applied_exposure"]), 6),
                "cash_ratio": round(float(row["cash_ratio"]), 6),
                "enabled_strategies": row["enabled_strategies"],
                "disabled_strategies": row["disabled_strategies"],
            }
        )
    return records


def run_shadow_backtest(
    survival_rows: list[dict[str, object]],
    benchmark_daily: pd.DataFrame,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    benchmark_code: str = DEFAULT_BENCHMARK_CODE,
    regime_field: str = "raw_regime",
    execution_lag_sessions: int = 1,
) -> dict[str, object]:
    decisions = build_daily_shadow_decisions(
        survival_rows,
        start_date=start_date,
        end_date=end_date,
        regime_field=regime_field,
    )
    benchmark = benchmark_returns_frame(benchmark_daily)
    merged = decisions.merge(benchmark, how="inner", on="date").sort_values("date").reset_index(drop=True)
    if merged.empty:
        raise ValueError("no overlapping dates between survival rows and benchmark data")

    lag = max(0, int(execution_lag_sessions))
    if lag:
        merged["applied_exposure"] = merged["r2_exposure"].shift(lag).fillna(merged["r2_exposure"])
    else:
        merged["applied_exposure"] = merged["r2_exposure"]

    merged["shadow_return"] = merged["applied_exposure"] * merged["benchmark_return"]
    merged["shadow_equity"] = (1.0 + merged["shadow_return"]).cumprod()
    merged["benchmark_equity"] = (1.0 + merged["benchmark_return"]).cumprod()
    merged["alpha"] = merged["shadow_equity"] - merged["benchmark_equity"]
    merged["daily_alpha_return"] = merged["shadow_return"] - merged["benchmark_return"]

    final_shadow = float(merged["shadow_equity"].iloc[-1])
    final_benchmark = float(merged["benchmark_equity"].iloc[-1])
    final_alpha = final_shadow - final_benchmark
    max_dd_shadow = _max_drawdown(merged["shadow_equity"])
    max_dd_benchmark = _max_drawdown(merged["benchmark_equity"])

    start = str(merged["date"].iloc[0])
    end = str(merged["date"].iloc[-1])
    summary = {
        "start_date": start,
        "end_date": end,
        "sessions": int(len(merged)),
        "benchmark_code": benchmark_code,
        "final_shadow_equity": round(final_shadow, 6),
        "final_benchmark_equity": round(final_benchmark, 6),
        "final_alpha": round(final_alpha, 6),
        "shadow_total_return": round(final_shadow - 1.0, 6),
        "benchmark_total_return": round(final_benchmark - 1.0, 6),
        "max_drawdown_shadow": max_dd_shadow,
        "max_drawdown_benchmark": max_dd_benchmark,
        "average_applied_exposure": round(float(merged["applied_exposure"].mean()), 6),
        "execution_lag_sessions": lag,
        "regime_field": regime_field,
    }

    return {
        "metadata": {
            "engine": "Shadow Portfolio Engine S1.1",
            "benchmark_code": benchmark_code,
            "regime_source": regime_field,
            "execution_lag_sessions": lag,
            "return_source": "Tushare fund_daily ETF quote returns; prefer pct_chg, then close/pre_close, with close pct_change only as fallback.",
            "evaluation_only": True,
            "no_prediction": True,
            "no_stock_selection": True,
            "no_trade_execution": True,
            "method": "Apply prior-session R2 exposure to 510500 daily returns and compare cumulative equity.",
        },
        "summary": summary,
        "shadow_equity_curve": _curve_records(merged, "shadow_equity"),
        "benchmark_equity_curve": _curve_records(merged, "benchmark_equity"),
        "shadow_returns": _return_records(merged, "shadow_return"),
        "benchmark_returns": _return_records(merged, "benchmark_return"),
        "alpha_series": _curve_records(merged, "alpha"),
        "daily_alpha_returns": _return_records(merged, "daily_alpha_return"),
        "decisions": _decision_records(merged),
        "final_alpha": summary["final_alpha"],
        "max_drawdown_shadow": summary["max_drawdown_shadow"],
        "max_drawdown_benchmark": summary["max_drawdown_benchmark"],
    }
