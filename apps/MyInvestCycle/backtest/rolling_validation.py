from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Mapping

import pandas as pd

from asset_opportunity.asset_loader import load_asset_history
from asset_opportunity.asset_registry import read_asset_registry
from backtest.alpha_portfolio_backtest import build_alpha_portfolio_backtest
from backtest.style_exposure_analysis import DEFAULT_ATTRIBUTION_PERIODS, STYLE_BENCHMARKS, build_style_exposure_analysis
from config import DATA_DIR
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "alpha_robustness_validation.json"
PRIMARY_MODE = "tradable_etf"
PRIMARY_STRATEGY = "router_selected_model_top3"
BASELINE_STRATEGY = "opportunity_score_top3"
REBALANCE_STEP = 60
TRANSACTION_COST = 0.001
MINIMUM_HOLDING_DAYS = 20


def _curve_metrics(curve: list[Mapping[str, object]]) -> dict[str, object]:
    if len(curve) < 2:
        return {}
    equity = pd.Series([float(row["equity"]) for row in curve])
    daily = equity.pct_change().fillna(0.0)
    total = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = max((len(curve) - 1) / 252.0, 1 / 252.0)
    cagr = (float(equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years)) - 1.0
    volatility = float(daily.std() * math.sqrt(252.0))
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    sharpe = cagr / volatility if volatility else None
    calmar = cagr / abs(max_drawdown) if max_drawdown else None
    return {
        "start": str(curve[0]["date"]),
        "end": str(curve[-1]["date"]),
        "observations": len(curve),
        "total_return": round(total, 6),
        "cagr": round(cagr, 6),
        "volatility": round(volatility, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe": None if sharpe is None else round(float(sharpe), 6),
        "calmar": None if calmar is None else round(float(calmar), 6),
    }


def _slice_curve(
    curve: list[Mapping[str, object]],
    start: str,
    end: str,
) -> list[dict[str, object]]:
    rows = [
        {"date": str(row["date"]), "equity": float(row["equity"])}
        for row in curve
        if start <= str(row["date"]) <= end
    ]
    if not rows:
        return []
    first = rows[0]["equity"]
    return [{"date": row["date"], "equity": round(row["equity"] / first, 6)} for row in rows]


def _asset_curve(code: str, start: str, end: str) -> dict[str, object]:
    assets = {asset.code: asset for asset in read_asset_registry()}
    asset = assets.get(code)
    if asset is None:
        return {"code": code, "available": False, "metrics": {}, "equity_curve": []}
    frame = load_asset_history(asset, start, end, cache_only=True)
    if frame.empty:
        return {"code": code, "name": asset.name, "available": False, "metrics": {}, "equity_curve": []}
    clean = frame[["trade_date", "close"]].copy()
    clean["trade_date"] = clean["trade_date"].astype(str)
    clean["close"] = pd.to_numeric(clean["close"], errors="coerce")
    clean = clean.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)
    first = float(clean["close"].iloc[0])
    curve = [
        {"date": str(row.trade_date), "equity": round(float(row.close) / first, 6)}
        for row in clean.itertuples()
    ]
    return {
        "code": code,
        "name": asset.name,
        "available": True,
        "coverage": {"start": str(clean["trade_date"].iloc[0]), "end": str(clean["trade_date"].iloc[-1]), "rows": len(clean)},
        "metrics": _curve_metrics(curve),
        "equity_curve": curve,
    }


def _period_exposure(style_exposure: Mapping[str, object], label: str) -> dict[str, object]:
    for period in style_exposure.get("periods") or []:
        if period.get("label") == label:
            return dict(period)
    return {}


def _spread(primary: Mapping[str, object], other: Mapping[str, object]) -> dict[str, object]:
    if not primary or not other:
        return {"cagr": None, "total_return": None, "sharpe": None}
    return {
        "cagr": None if primary.get("cagr") is None or other.get("cagr") is None else round(float(primary["cagr"]) - float(other["cagr"]), 6),
        "total_return": None if primary.get("total_return") is None or other.get("total_return") is None else round(float(primary["total_return"]) - float(other["total_return"]), 6),
        "sharpe": None if primary.get("sharpe") is None or other.get("sharpe") is None else round(float(primary["sharpe"]) - float(other["sharpe"]), 6),
    }


def build_alpha_robustness_validation(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
) -> dict[str, object]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    portfolio = build_alpha_portfolio_backtest(
        start_date=start,
        end_date=end,
        step_sessions=REBALANCE_STEP,
        transaction_cost=TRANSACTION_COST,
    )
    style_exposure = build_style_exposure_analysis(
        start_date=start,
        end_date=end,
        step_sessions=REBALANCE_STEP,
        model_label="router_selected_model",
        top_n=3,
    )
    primary_curve = portfolio["strategies"][PRIMARY_MODE][PRIMARY_STRATEGY]["equity_curve"]
    baseline_curve = portfolio["strategies"][PRIMARY_MODE][BASELINE_STRATEGY]["equity_curve"]
    broad_benchmarks = {
        code: item["equity_curve"]
        for code, item in portfolio.get("benchmarks", {}).items()
    }
    style_benchmarks = {
        item["code"]: _asset_curve(item["code"], start, end)
        for item in STYLE_BENCHMARKS
    }

    period_results: list[dict[str, object]] = []
    for period in DEFAULT_ATTRIBUTION_PERIODS:
        period_start = normalize_trade_date(period["start"])
        period_end = min(normalize_trade_date(period["end"]), end)
        primary_metrics = _curve_metrics(_slice_curve(primary_curve, period_start, period_end))
        baseline_metrics = _curve_metrics(_slice_curve(baseline_curve, period_start, period_end))
        broad_metrics = {
            code: _curve_metrics(_slice_curve(curve, period_start, period_end))
            for code, curve in broad_benchmarks.items()
        }
        style_metrics = {
            code: {
                "name": style_benchmarks[code].get("name"),
                "style": next((item["style"] for item in STYLE_BENCHMARKS if item["code"] == code), None),
                "coverage": style_benchmarks[code].get("coverage"),
                "metrics": _curve_metrics(_slice_curve(style_benchmarks[code].get("equity_curve") or [], period_start, period_end)),
            }
            for code in style_benchmarks
        }
        spreads = {
            "vs_opportunity_score_top3": _spread(primary_metrics, baseline_metrics),
            **{
                f"vs_{code}": _spread(primary_metrics, metrics)
                for code, metrics in broad_metrics.items()
            },
            **{
                f"vs_{code}": _spread(primary_metrics, item["metrics"])
                for code, item in style_metrics.items()
            },
        }
        exposure = _period_exposure(style_exposure, str(period["label"]))
        period_results.append(
            {
                "label": period["label"],
                "window": {"start": period_start, "end": period_end},
                "portfolio": primary_metrics,
                "opportunity_score_top3": baseline_metrics,
                "broad_benchmarks": broad_metrics,
                "style_benchmarks": style_metrics,
                "style_exposure": exposure,
                "spreads": spreads,
            }
        )

    growth_exposure_periods = [
        period["label"] for period in period_results
        if ((period.get("style_exposure") or {}).get("dominant_style") or {}).get("style") == "growth_technology"
        and float(((period.get("style_exposure") or {}).get("dominant_style") or {}).get("share") or 0.0) >= 0.67
    ]
    latest_dominant = (style_exposure.get("latest_exposure") or {}).get("dominant") or {}
    latest_growth_warning = (
        latest_dominant.get("style") == "growth_technology"
        and float(latest_dominant.get("share") or 0.0) >= 0.67
    )
    positive_vs_510500 = [
        period["label"] for period in period_results
        if ((period.get("spreads") or {}).get("vs_510500.SH") or {}).get("cagr") is not None
        and float(((period.get("spreads") or {}).get("vs_510500.SH") or {}).get("cagr")) > 0
    ]
    return {
        "metadata": {
            "engine": "V3.4.4 Alpha Portfolio Robustness & Style Attribution Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start, "end": end},
            "primary_series": f"{PRIMARY_MODE}.{PRIMARY_STRATEGY}",
            "rebalance_step": REBALANCE_STEP,
            "transaction_cost": TRANSACTION_COST,
            "minimum_holding_days": MINIMUM_HOLDING_DAYS,
        },
        "periods": period_results,
        "style_exposure": style_exposure,
        "style_benchmark_universe": list(STYLE_BENCHMARKS),
        "summary": {
            "positive_vs_510500_periods": positive_vs_510500,
            "growth_technology_dominant_periods": growth_exposure_periods,
            "latest_dominant_style": latest_dominant,
            "style_beta_warning": bool(growth_exposure_periods or latest_growth_warning),
            "interpretation": "If growth_technology dominates exposure and style benchmarks explain returns, treat gains as style beta until out-of-sample evidence proves otherwise.",
        },
        "constraints": {
            "analysis_only": True,
            "model_unchanged": True,
            "router_unchanged": True,
            "top_n_unchanged": True,
            "step60_not_promoted_to_default": True,
            "no_parameter_optimization": True,
            "no_best_parameter_selection": True,
            "no_theme_cap": True,
            "no_allocation": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def write_alpha_robustness_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
