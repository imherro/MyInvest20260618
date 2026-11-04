from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd

from backtest.execution_simulator import execution_cost
from backtest.metrics import calculate_metrics
from data.trade_calendar import format_api_date
from engine.data_loader import MarketData


class _StaticMarketDataLoader:
    def __init__(self, market_data: MarketData) -> None:
        self.market_data = market_data

    def load_market_data(self, trade_date: str | None = None) -> MarketData:
        return self.market_data


def build_shadow_portfolio(
    market_data: MarketData,
    top_n: int,
    lookback_days: int = 10,
) -> dict[str, Any]:
    if lookback_days <= 0:
        return _empty_shadow_portfolio(lookback_days, "disabled")
    if market_data.daily.empty:
        return _empty_shadow_portfolio(lookback_days, "no daily data")

    daily = market_data.daily.copy()
    daily["trade_date"] = daily["trade_date"].astype(str)
    trade_dates = sorted(
        date
        for date in daily["trade_date"].dropna().unique().tolist()
        if str(date) <= str(market_data.trade_date)
    )
    if len(trade_dates) < 2:
        return _empty_shadow_portfolio(lookback_days, "not enough trade dates")

    pairs = list(zip(trade_dates[:-1], trade_dates[1:]))[-lookback_days:]
    nav = 1.0
    peak = 1.0
    total_turnover = 0.0
    current_weights: dict[str, float] = {}
    equity_curve = [{"date": format_api_date(pairs[0][0]), "nav": nav}]
    drawdown_curve = [{"date": format_api_date(pairs[0][0]), "drawdown": 0.0}]
    rebalance_history = []

    for rebalance_date, applied_date in pairs:
        sliced = _slice_market_data(market_data, rebalance_date)
        payload = _build_daily_payload(sliced, top_n)
        signals = payload.get("signals", [])
        target_weights = _target_weights(signals)
        turnover = _turnover(current_weights, target_weights)
        total_turnover += turnover
        cost = execution_cost(turnover)
        portfolio_return = _portfolio_return(daily, applied_date, target_weights)
        nav = nav * (1 + portfolio_return - cost)
        peak = max(peak, nav)
        drawdown = nav / peak - 1 if peak else 0.0

        equity_curve.append({"date": format_api_date(applied_date), "nav": round(nav, 6)})
        drawdown_curve.append(
            {"date": format_api_date(applied_date), "drawdown": round(drawdown, 6)}
        )
        rebalance_history.append(
            {
                "rebalance_date": format_api_date(rebalance_date),
                "applied_date": format_api_date(applied_date),
                "nav": round(nav, 6),
                "target_exposure": round(sum(target_weights.values()), 6),
                "turnover": round(turnover, 6),
                "cost": round(cost, 6),
                "portfolio_return": round(portfolio_return, 6),
                "signal_counts": payload.get("signal_summary", {}).get("counts", {}),
                "changes": _rebalance_changes(current_weights, target_weights, signals),
            }
        )
        current_weights = _drift_weights(target_weights, daily, applied_date)

    metrics = calculate_metrics(equity_curve, drawdown_curve, total_turnover)
    return {
        "status": "ok",
        "mode": "shadow",
        "lookback_days": lookback_days,
        "assumptions": {
            "rebalance": "daily_full_invested_target_portfolio_applied_next_trade_day",
            "position_source": "target portfolio weights normalized to 100%",
            "initial_nav": 1.0,
            "target_exposure": 1.0,
            "ratio_only": True,
        },
        "summary": {
            "start_date": equity_curve[0]["date"],
            "end_date": equity_curve[-1]["date"],
            "start_nav": equity_curve[0]["nav"],
            "end_nav": equity_curve[-1]["nav"],
            "total_return": round(equity_curve[-1]["nav"] / equity_curve[0]["nav"] - 1, 6),
            "max_drawdown": metrics["max_drawdown"],
            "total_turnover": metrics["turnover"],
            "rebalance_count": len(rebalance_history),
            "latest_exposure": rebalance_history[-1]["target_exposure"]
            if rebalance_history
            else 0.0,
            "latest_position_count": len(current_weights),
        },
        "metrics": metrics,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "rebalance_history": rebalance_history,
    }


def _build_daily_payload(market_data: MarketData, top_n: int) -> dict[str, Any]:
    from strategy.core_strategy import build_stock_picks

    return build_stock_picks(
        trade_date=market_data.trade_date,
        top_n=top_n,
        loader=_StaticMarketDataLoader(market_data),
        shadow_days=0,
        save_snapshot=False,
    )


def _slice_market_data(market_data: MarketData, trade_date: str) -> MarketData:
    daily = market_data.daily.copy()
    daily["trade_date"] = daily["trade_date"].astype(str)
    daily = daily[daily["trade_date"] <= trade_date]
    return replace(
        market_data,
        trade_date=trade_date,
        daily=daily,
        daily_basic=_latest_as_of(market_data.daily_basic, trade_date, "trade_date"),
        financial_indicator=_latest_as_of(
            market_data.financial_indicator,
            trade_date,
            "end_date",
        ),
    )


def _latest_as_of(frame: pd.DataFrame, trade_date: str, date_column: str) -> pd.DataFrame:
    if frame.empty or date_column not in frame.columns:
        return frame.copy()
    sliced = frame.copy()
    sliced[date_column] = sliced[date_column].astype(str)
    historical = sliced[sliced[date_column] <= trade_date]
    if historical.empty:
        return sliced
    return historical


def _target_weights(signals: list[dict[str, Any]]) -> dict[str, float]:
    targets = {}
    for signal in signals:
        code = str(signal.get("code") or "")
        weight = float(signal.get("position_size") or 0)
        if code and signal.get("action") == "BUY" and weight > 0:
            targets[code] = round(weight, 6)
    return _normalize_full_exposure(targets)


def _portfolio_return(
    daily: pd.DataFrame,
    applied_date: str,
    target_weights: dict[str, float],
) -> float:
    if not target_weights:
        return 0.0
    day = daily[daily["trade_date"].astype(str) == applied_date].copy()
    if day.empty:
        return 0.0
    day["pct_chg"] = pd.to_numeric(day.get("pct_chg"), errors="coerce").fillna(0) / 100.0
    returns = dict(zip(day["ts_code"].astype(str), day["pct_chg"]))
    return sum(weight * float(returns.get(code, 0.0)) for code, weight in target_weights.items())


def _turnover(current_weights: dict[str, float], target_weights: dict[str, float]) -> float:
    codes = set(current_weights) | set(target_weights)
    return round(
        sum(abs(target_weights.get(code, 0.0) - current_weights.get(code, 0.0)) for code in codes)
        / 2,
        6,
    )


def _rebalance_changes(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    signal_by_code = {str(signal.get("code") or ""): signal for signal in signals}
    changes = []
    for code in sorted(set(current_weights) | set(target_weights)):
        previous = round(current_weights.get(code, 0.0), 6)
        target = round(target_weights.get(code, 0.0), 6)
        delta = round(target - previous, 6)
        if abs(delta) < 0.000001:
            continue
        signal = signal_by_code.get(code, {})
        changes.append(
            {
                "code": code,
                "name": signal.get("name"),
                "previous_weight": previous,
                "target_weight": target,
                "change": delta,
                "action": signal.get("action") or ("SELL" if target == 0 else "BUY"),
                "confidence": signal.get("confidence"),
                "final_score": signal.get("final_score"),
            }
        )
    return sorted(changes, key=lambda item: (-abs(float(item["change"])), item["code"]))


def _drift_weights(
    target_weights: dict[str, float],
    daily: pd.DataFrame,
    applied_date: str,
) -> dict[str, float]:
    if not target_weights:
        return {}
    day = daily[daily["trade_date"].astype(str) == applied_date].copy()
    day["pct_chg"] = pd.to_numeric(day.get("pct_chg"), errors="coerce").fillna(0) / 100.0
    returns = dict(zip(day["ts_code"].astype(str), day["pct_chg"]))
    drifted = {
        code: weight * (1 + float(returns.get(code, 0.0)))
        for code, weight in target_weights.items()
    }
    total = sum(drifted.values())
    if total <= 0:
        return {}
    exposure = sum(target_weights.values())
    return {code: round(weight / total * exposure, 6) for code, weight in drifted.items()}


def _normalize_full_exposure(weights: dict[str, float]) -> dict[str, float]:
    total = sum(float(weight) for weight in weights.values())
    if total <= 0:
        return {}
    normalized = {
        code: round(float(weight) / total, 6)
        for code, weight in sorted(weights.items())
    }
    drift = round(1.0 - sum(normalized.values()), 6)
    if normalized and abs(drift) >= 0.000001:
        largest = max(normalized, key=normalized.get)
        normalized[largest] = round(normalized[largest] + drift, 6)
    return normalized


def _empty_shadow_portfolio(lookback_days: int, reason: str) -> dict[str, Any]:
    return {
        "status": "empty",
        "mode": "shadow",
        "lookback_days": lookback_days,
        "reason": reason,
        "summary": {
            "start_nav": 1.0,
            "end_nav": 1.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "total_turnover": 0.0,
            "rebalance_count": 0,
            "latest_exposure": 0.0,
            "latest_position_count": 0,
        },
        "assumptions": {
            "rebalance": "daily_full_invested_target_portfolio_applied_next_trade_day",
            "position_source": "target portfolio weights normalized to 100%",
            "initial_nav": 1.0,
            "target_exposure": 1.0,
            "ratio_only": True,
        },
        "metrics": {},
        "equity_curve": [],
        "drawdown_curve": [],
        "rebalance_history": [],
    }
