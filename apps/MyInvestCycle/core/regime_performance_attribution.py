from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from config import DATA_DIR
from core.data_loader import normalize_trade_date


DEFAULT_SHADOW_BACKTEST_PATH = DATA_DIR / "shadow_equity_curve.json"
REGIME_ORDER = ("bull", "range", "bear", "transition")


def load_shadow_backtest(path: str | Path = DEFAULT_SHADOW_BACKTEST_PATH) -> dict[str, object]:
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"shadow backtest file not found: {source_path}")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"shadow backtest payload must be an object: {source_path}")
    return payload


def _records_frame(payload: Mapping[str, object], key: str, value_name: str, source_name: str) -> pd.DataFrame:
    records = payload.get(key)
    if not isinstance(records, list):
        raise ValueError(f"shadow backtest missing {key}")
    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame(columns=["date", value_name])
    if source_name not in frame.columns:
        raise ValueError(f"{key} missing {source_name}")
    return frame[["date", source_name]].rename(columns={source_name: value_name})


def shadow_backtest_frame(
    payload: Mapping[str, object],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    decisions = pd.DataFrame(payload.get("decisions") or [])
    if decisions.empty:
        raise ValueError("shadow backtest missing decisions")

    frame = decisions[
        [
            "date",
            "regime",
            "risk_level",
            "risk_score",
            "signal_exposure",
            "applied_exposure",
            "cash_ratio",
        ]
    ].copy()
    frame = frame.merge(_records_frame(payload, "shadow_returns", "shadow_return", "return"), on="date")
    frame = frame.merge(_records_frame(payload, "benchmark_returns", "benchmark_return", "return"), on="date")
    frame = frame.merge(_records_frame(payload, "shadow_equity_curve", "shadow_equity", "value"), on="date")
    frame = frame.merge(_records_frame(payload, "benchmark_equity_curve", "benchmark_equity", "value"), on="date")

    daily_alpha = _records_frame(payload, "daily_alpha_returns", "daily_alpha_return", "return")
    if daily_alpha.empty:
        frame["daily_alpha_return"] = frame["shadow_return"] - frame["benchmark_return"]
    else:
        frame = frame.merge(daily_alpha, on="date")

    if start_date:
        start = normalize_trade_date(start_date)
        frame = frame[frame["date"].astype(str) >= start]
    if end_date:
        end = normalize_trade_date(end_date)
        frame = frame[frame["date"].astype(str) <= end]

    if frame.empty:
        raise ValueError("no shadow backtest rows in requested window")

    numeric_columns = [
        "risk_score",
        "signal_exposure",
        "applied_exposure",
        "cash_ratio",
        "shadow_return",
        "benchmark_return",
        "shadow_equity",
        "benchmark_equity",
        "daily_alpha_return",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["date", "regime", "shadow_return", "benchmark_return"])
    return frame.sort_values("date").reset_index(drop=True)


def _compound_return(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    return float((1.0 + returns).prod() - 1.0)


def _max_drawdown_from_returns(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    equity = (1.0 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    return float(drawdown.min())


def _return_drawdown_ratio(total_return: float, max_drawdown: float) -> float | None:
    drawdown_abs = abs(max_drawdown)
    if drawdown_abs < 1e-12:
        return None
    return total_return / drawdown_abs


def _round_or_none(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _regime_role(regime: str, benchmark_return: float, alpha: float) -> str:
    if alpha >= 0 and benchmark_return < 0:
        return "downside_protection"
    if alpha >= 0:
        return "positive_alpha"
    if regime == "bull" and benchmark_return > 0:
        return "upside_participation_drag"
    if alpha < 0:
        return "defensive_cost"
    return "neutral"


def _regime_stats(regime: str, frame: pd.DataFrame, total_daily_alpha: float) -> dict[str, object]:
    shadow_return = _compound_return(frame["shadow_return"])
    benchmark_return = _compound_return(frame["benchmark_return"])
    alpha = shadow_return - benchmark_return
    daily_alpha_contribution = float(frame["daily_alpha_return"].sum())
    max_dd_shadow = _max_drawdown_from_returns(frame["shadow_return"])
    max_dd_benchmark = _max_drawdown_from_returns(frame["benchmark_return"])
    share_denominator = total_daily_alpha if abs(total_daily_alpha) > 1e-12 else None

    return {
        "regime": regime,
        "sessions": int(len(frame)),
        "shadow_return": round(shadow_return, 6),
        "benchmark_return": round(benchmark_return, 6),
        "alpha": round(alpha, 6),
        "daily_alpha_contribution": round(daily_alpha_contribution, 6),
        "daily_alpha_share": _round_or_none(daily_alpha_contribution / share_denominator if share_denominator else None),
        "avg_applied_exposure": round(float(frame["applied_exposure"].mean()), 6),
        "avg_risk_score": round(float(frame["risk_score"].mean()), 6),
        "max_drawdown_shadow": round(max_dd_shadow, 6),
        "max_drawdown_benchmark": round(max_dd_benchmark, 6),
        "shadow_return_drawdown_ratio": _round_or_none(_return_drawdown_ratio(shadow_return, max_dd_shadow)),
        "benchmark_return_drawdown_ratio": _round_or_none(_return_drawdown_ratio(benchmark_return, max_dd_benchmark)),
        "role": _regime_role(regime, benchmark_return, alpha),
    }


def build_regime_performance_attribution(
    payload: Mapping[str, object],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    frame = shadow_backtest_frame(payload, start_date=start_date, end_date=end_date)
    total_daily_alpha = float(frame["daily_alpha_return"].sum())
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}

    regime_performance: dict[str, dict[str, object]] = {}
    for regime in REGIME_ORDER:
        group = frame[frame["regime"] == regime]
        if group.empty:
            continue
        regime_performance[regime] = _regime_stats(regime, group, total_daily_alpha)

    ranked = sorted(
        regime_performance.values(),
        key=lambda item: float(item["daily_alpha_contribution"]),
    )
    largest_drag = ranked[0]["regime"] if ranked else None
    largest_positive = ranked[-1]["regime"] if ranked and float(ranked[-1]["daily_alpha_contribution"]) > 0 else None
    shadow_dd = float(summary.get("max_drawdown_shadow", 0.0) or 0.0)
    benchmark_dd = float(summary.get("max_drawdown_benchmark", 0.0) or 0.0)
    drawdown_reduction = abs(benchmark_dd) - abs(shadow_dd)

    return {
        "metadata": {
            "engine": "Regime-Based Performance Attribution S1.2",
            "source": "data/shadow_equity_curve.json",
            "evaluation_only": True,
            "no_prediction": True,
            "no_stock_selection": True,
            "no_trade_execution": True,
            "method": "Group S1.1 shadow and benchmark daily returns by regime and compare compounded return, drawdown, and daily alpha contribution.",
        },
        "summary": {
            "start_date": str(frame["date"].iloc[0]),
            "end_date": str(frame["date"].iloc[-1]),
            "sessions": int(len(frame)),
            "total_alpha": round(float(summary.get("final_alpha", frame["shadow_equity"].iloc[-1] - frame["benchmark_equity"].iloc[-1])), 6),
            "additive_daily_alpha": round(total_daily_alpha, 6),
            "shadow_total_return": round(float(summary.get("shadow_total_return", frame["shadow_equity"].iloc[-1] - 1.0)), 6),
            "benchmark_total_return": round(float(summary.get("benchmark_total_return", frame["benchmark_equity"].iloc[-1] - 1.0)), 6),
            "max_drawdown_shadow": round(shadow_dd, 6),
            "max_drawdown_benchmark": round(benchmark_dd, 6),
            "drawdown_reduction": round(drawdown_reduction, 6),
            "largest_drag_regime": largest_drag,
            "largest_positive_regime": largest_positive,
        },
        "regime_performance": regime_performance,
        "ranked_contributions": [
            {
                "regime": item["regime"],
                "daily_alpha_contribution": item["daily_alpha_contribution"],
                "alpha": item["alpha"],
                "role": item["role"],
            }
            for item in ranked
        ],
    }
