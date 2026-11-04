from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from asset_opportunity.asset_loader import load_asset_history
from asset_opportunity.asset_registry import read_asset_registry
from asset_opportunity.residual_alpha_analysis import fit_linear_factor_model, metrics_from_returns
from backtest.alpha_portfolio_backtest import build_alpha_portfolio_backtest
from backtest.style_exposure_analysis import DEFAULT_ATTRIBUTION_PERIODS
from config import DATA_DIR
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "residual_alpha_analysis.json"
PRIMARY_MODE = "tradable_etf"
PRIMARY_STRATEGY = "router_selected_model_top3"
REBALANCE_STEP = 60
TRANSACTION_COST = 0.001
FACTOR_DEFINITIONS = (
    {"code": "510300.SH", "name": "沪深300ETF", "factor": "market_large"},
    {"code": "510500.SH", "name": "中证500ETF", "factor": "mid_small"},
    {"code": "159915.SZ", "name": "创业板ETF", "factor": "growth_chinext"},
    {"code": "588000.SH", "name": "科创50ETF", "factor": "growth_star50"},
    {"code": "512480.SH", "name": "半导体ETF", "factor": "semiconductor"},
    {"code": "510880.SH", "name": "红利ETF", "factor": "dividend_value"},
)


def _curve_returns(curve: list[Mapping[str, object]], name: str) -> pd.DataFrame:
    if not curve:
        return pd.DataFrame(columns=["date", name])
    frame = pd.DataFrame(
        {
            "date": [str(row["date"]) for row in curve],
            "equity": [float(row["equity"]) for row in curve],
        }
    )
    frame[name] = frame["equity"].pct_change()
    return frame.dropna(subset=[name])[["date", name]]


def _asset_returns(code: str, start: str, end: str, factor_name: str) -> dict[str, object]:
    assets = {asset.code: asset for asset in read_asset_registry()}
    asset = assets.get(code)
    if asset is None:
        return {"code": code, "factor": factor_name, "available": False, "returns": pd.DataFrame(columns=["date", factor_name])}
    frame = load_asset_history(asset, start, end, cache_only=True)
    if frame.empty:
        return {"code": code, "name": asset.name, "factor": factor_name, "available": False, "returns": pd.DataFrame(columns=["date", factor_name])}
    clean = frame[["trade_date", "close"]].copy()
    clean["date"] = clean["trade_date"].astype(str)
    clean["close"] = pd.to_numeric(clean["close"], errors="coerce")
    clean = clean.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    clean[factor_name] = clean["close"].pct_change()
    returns = clean.dropna(subset=[factor_name])[["date", factor_name]]
    return {
        "code": code,
        "name": asset.name,
        "factor": factor_name,
        "available": True,
        "coverage": {"start": str(clean["date"].iloc[0]), "end": str(clean["date"].iloc[-1]), "rows": len(clean)},
        "returns": returns,
    }


def _join_factor_frame(target: pd.DataFrame, factors: list[dict[str, object]]) -> pd.DataFrame:
    joined = target.copy()
    for factor in factors:
        returns = factor.get("returns")
        if isinstance(returns, pd.DataFrame) and not returns.empty:
            joined = joined.merge(returns, on="date", how="left")
    return joined.set_index("date").sort_index()


def _period_frame(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return frame[(frame.index >= start) & (frame.index <= end)].copy()


def _strip_model(model: dict[str, object]) -> dict[str, object]:
    return {
        key: value for key, value in model.items()
        if key not in {"neutralized_returns", "dates"}
    }


def build_residual_alpha_analysis(
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
    target_curve = portfolio["strategies"][PRIMARY_MODE][PRIMARY_STRATEGY]["equity_curve"]
    target_returns = _curve_returns(target_curve, "portfolio")
    factor_payloads = [
        _asset_returns(item["code"], start, end, item["factor"])
        for item in FACTOR_DEFINITIONS
    ]
    factor_cols = [
        str(item["factor"]) for item in FACTOR_DEFINITIONS
        if any(payload.get("factor") == item["factor"] and payload.get("available") for payload in factor_payloads)
    ]
    factor_frame = _join_factor_frame(target_returns, factor_payloads)

    periods: list[dict[str, object]] = []
    for period in DEFAULT_ATTRIBUTION_PERIODS:
        period_start = normalize_trade_date(period["start"])
        period_end = min(normalize_trade_date(period["end"]), end)
        frame = _period_frame(factor_frame, period_start, period_end)
        model = fit_linear_factor_model(frame, target_col="portfolio", factor_cols=factor_cols)
        neutralized_metrics = {}
        if model.get("available"):
            neutralized_metrics = metrics_from_returns(
                list(model["dates"]),
                model["neutralized_returns"],
            )
        portfolio_metrics = metrics_from_returns(
            frame.dropna(subset=["portfolio"]).index.astype(str).tolist(),
            frame.dropna(subset=["portfolio"])["portfolio"].astype(float).tolist(),
        )
        periods.append(
            {
                "label": period["label"],
                "window": {"start": period_start, "end": period_end},
                "portfolio_metrics": portfolio_metrics,
                "factor_model": _strip_model(model),
                "factor_neutral_residual_metrics": neutralized_metrics,
            }
        )

    positive_residual_periods = [
        period["label"] for period in periods
        if (period.get("factor_neutral_residual_metrics") or {}).get("cagr") is not None
        and float((period.get("factor_neutral_residual_metrics") or {}).get("cagr")) > 0
    ]
    residual_cagr_by_period = {
        str(period["label"]): (period.get("factor_neutral_residual_metrics") or {}).get("cagr")
        for period in periods
    }
    economically_meaningful = [
        label for label, cagr in residual_cagr_by_period.items()
        if cagr is not None and float(cagr) >= 0.05
    ]
    return {
        "metadata": {
            "engine": "V3.4.5 Residual Alpha Attribution & Factor Neutralization Analysis",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start, "end": end},
            "primary_series": f"{PRIMARY_MODE}.{PRIMARY_STRATEGY}",
            "rebalance_step": REBALANCE_STEP,
            "transaction_cost": TRANSACTION_COST,
        },
        "factor_universe": [
            {
                key: value for key, value in payload.items()
                if key != "returns"
            }
            for payload in factor_payloads
        ],
        "periods": periods,
        "summary": {
            "positive_residual_alpha_periods": positive_residual_periods,
            "residual_alpha_persistent": len(positive_residual_periods) == len(periods),
            "residual_cagr_by_period": residual_cagr_by_period,
            "economically_meaningful_residual_alpha_periods": economically_meaningful,
            "economic_strength": "strong" if len(economically_meaningful) >= 3 else "weak_or_inconclusive",
            "interpretation": "Residual alpha is the factor-neutralized return after removing fitted market and style factor returns; this is an in-sample attribution, not a prediction.",
        },
        "constraints": {
            "analysis_only": True,
            "ordinary_linear_regression_only": True,
            "no_machine_learning_prediction": True,
            "model_unchanged": True,
            "router_unchanged": True,
            "top_n_unchanged": True,
            "step60_not_promoted_to_default": True,
            "no_parameter_optimization": True,
            "no_theme_cap": True,
            "no_allocation": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def write_residual_alpha_analysis(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
