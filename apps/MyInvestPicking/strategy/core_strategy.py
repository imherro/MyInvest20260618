from __future__ import annotations

from typing import Any

import pandas as pd

from backtest.engine import run_backtest
from config.settings import DEFAULT_TOP_N
from engine.data_loader import TushareDataLoader, format_api_date
from engine.factor_decay import add_factor_health, summarize_factor_health
from engine.factor_engine import compute_factors
from engine.final_decision_engine import (
    build_final_signals,
    summarize_gate_status,
    summarize_signals,
)
from engine.liquidity import filter_liquidity
from engine.market_features import compute_market_features
from engine.portfolio_stability import compute_portfolio_stability
from engine.scoring import GROWTH_TREND_WEIGHTS, score_stocks
from engine.shadow_portfolio import build_shadow_portfolio
from engine.snapshot import build_universe_hash, create_snapshot
from engine.universe import filter_universe
from risk.concentration_risk import evaluate_concentration_risk
from risk.correlation_engine import compute_correlation_risk
from risk.dynamic_risk_allocator import allocate_dynamic_risk_budget
from risk.risk_engine import build_risk_managed_portfolio


def _round_float(value: Any, digits: int = 4) -> float | None:
    if pd.isna(value):
        return None
    return round(float(value), digits)


def _to_pick(
    row: pd.Series,
    *,
    candidate_style: str = "composite",
    candidate_score_column: str = "score",
) -> dict[str, Any]:
    factors = {
        "momentum": _round_float(row.get("momentum")),
        "trend": _round_float(row.get("trend")),
        "growth": _round_float(row.get("growth")),
        "growth_data_quality": _round_float(row.get("growth_data_quality")),
        "quality": _round_float(row.get("quality")),
        "value": _round_float(row.get("value")),
        "risk": _round_float(row.get("risk")),
        "industry_strength": _round_float(row.get("industry_strength")),
        "growth_industry_profile": _round_float(row.get("growth_industry_profile")),
        "growth_theme_profile": _round_float(row.get("growth_theme_profile")),
    }
    candidate_scores = {
        "value": _round_float(row.get("value_candidate_score")),
        "growth": _round_float(row.get("growth_candidate_score")),
        "trend": _round_float(row.get("trend_candidate_score")),
        "composite": _round_float(row.get("score")),
    }
    return {
        "code": row["ts_code"],
        "name": row.get("name"),
        "industry": row.get("industry"),
        "candidate_style": candidate_style,
        "candidate_score": _round_float(row.get(candidate_score_column)),
        "candidate_scores": candidate_scores,
        "score": _round_float(row.get("score")),
        "final_score": _round_float(row.get("final_score")),
        "risk_adjust_factor": _round_float(row.get("risk_adjust_factor")),
        "regime_multiplier": _round_float(row.get("regime_multiplier")),
        "factor_health_score": _round_float(row.get("factor_health_score")),
        "exchange_risk_multiplier": _round_float(row.get("exchange_risk_multiplier")),
        "liquidity_risk_multiplier": _round_float(row.get("liquidity_risk_multiplier")),
        "factors": factors,
        "contribution": {
            "momentum": _round_float(row.get("momentum_contribution")),
            "trend": _round_float(row.get("trend_contribution")),
            "growth": _round_float(row.get("growth_contribution")),
            "quality": _round_float(row.get("quality_contribution")),
            "value": _round_float(row.get("value_contribution")),
            "risk": _round_float(row.get("risk_contribution")),
            "industry_strength": _round_float(row.get("industry_strength_contribution")),
        },
        "metrics": {
            "momentum_5d": _round_float(row.get("momentum_5d")),
            "momentum_20d": _round_float(row.get("momentum_20d")),
            "momentum_60d": _round_float(row.get("momentum_60d")),
            "momentum_120d": _round_float(row.get("momentum_120d")),
            "volatility_20d": _round_float(row.get("volatility_20d")),
            "amount_expansion_20d": _round_float(row.get("amount_expansion_20d")),
            "high_120_distance": _round_float(row.get("high_120_distance")),
            "observation_count": _round_float(row.get("observation_count"), 0),
            "latest_amount": _round_float(row.get("latest_amount")),
            "latest_vol": _round_float(row.get("latest_vol")),
            "latest_pct_chg": _round_float(row.get("latest_pct_chg")),
            "roe": _round_float(row.get("roe")),
            "roe_improvement": _round_float(row.get("roe_improvement")),
            "growth_data_quality": _round_float(row.get("growth_data_quality")),
            "growth_industry_profile": _round_float(row.get("growth_industry_profile")),
            "growth_theme_profile": _round_float(row.get("growth_theme_profile")),
            "theme_tags": row.get("theme_tags") or "",
            "theme_source": row.get("theme_source") or "none",
            "revenue_growth_yoy": _round_float(row.get("revenue_growth_yoy")),
            "net_profit_growth_yoy": _round_float(row.get("net_profit_growth_yoy")),
            "ocf_to_profit": _round_float(row.get("ocf_to_profit")),
            "pe": _round_float(row.get("pe")),
            "pb": _round_float(row.get("pb")),
            "close": _round_float(row.get("close")),
            "turnover_rate": _round_float(row.get("turnover_rate")),
            "volume_ratio": _round_float(row.get("volume_ratio")),
            "list_age_days": _round_float(row.get("list_age_days"), 0),
            "industry_relative_strength": _round_float(row.get("industry_relative_strength")),
        },
        "reason": _build_reason(factors),
    }


def _build_reason(factors: dict[str, float | None]) -> list[str]:
    readable = []
    labels = {
        "momentum": "Momentum",
        "trend": "Trend",
        "growth": "Growth",
        "quality": "Quality",
        "value": "Valuation",
        "risk": "Risk control",
        "industry_strength": "Industry strength",
        "growth_industry_profile": "Growth industry fit",
        "growth_theme_profile": "Growth theme fit",
    }
    for key, label in labels.items():
        value = factors.get(key)
        if value is not None:
            readable.append(f"{label} rank {value:.2f}")
    return readable


def build_stock_picks(
    trade_date: str | None = None,
    top_n: int = DEFAULT_TOP_N,
    loader: TushareDataLoader | None = None,
    shadow_days: int = 10,
    save_snapshot: bool = True,
) -> dict[str, Any]:
    active_loader = loader or TushareDataLoader()
    market_data = active_loader.load_market_data(trade_date)
    market_features = compute_market_features(market_data.daily)
    market_regime = {
        "state": "ignored",
        "confidence": 1.0,
        "reason": "full_invested_shadow_portfolio",
        **market_features,
    }
    risk_budget = allocate_dynamic_risk_budget(market_regime)
    if top_n > 0:
        risk_budget["max_position_per_stock"] = max(
            float(risk_budget["max_position_per_stock"]),
            round(1.0 / top_n, 6),
        )
    portfolio_mode = {
        "name": "full_invested_shadow_portfolio",
        "target_exposure": 1.0,
        "market_factors_used_for_exposure": False,
        "rebalance": "daily_target_portfolio",
    }
    tradable_universe = filter_universe(market_data.stock_basic, market_data.daily)
    tradable_codes = set(tradable_universe["ts_code"].astype(str))

    factors = compute_factors(market_data)
    if not factors.empty:
        factors = factors[factors["ts_code"].isin(tradable_codes)]
    factors = filter_liquidity(factors)
    factors = add_factor_health(factors)
    factor_health = summarize_factor_health(factors)

    scored = score_stocks(factors, regime_state=str(market_regime["state"]))
    selected = scored.head(max(top_n, 0))
    results = [_to_pick(row) for _, row in selected.iterrows()]
    candidate_pools = _build_candidate_pools(scored, max(top_n, 0))
    correlation_risk = compute_correlation_risk(
        market_data.daily,
        [pick["code"] for pick in results],
    )
    portfolio_result = build_risk_managed_portfolio(
        results,
        risk_budget=risk_budget,
        correlation_clusters=correlation_risk["clusters"],
    )
    concentration_risk = evaluate_concentration_risk(
        portfolio_result["positions"],
        correlation_risk["clusters"],
    )
    portfolio_stability = compute_portfolio_stability(portfolio_result["positions"])
    backtest = run_backtest(market_data, portfolio_result["positions"])
    signals = build_final_signals(
        portfolio_result["positions"],
        market_regime=market_regime,
        correlation_risk=correlation_risk,
        backtest_metrics=backtest["metrics"],
    )
    signal_summary = summarize_signals(signals)
    gate_summary = summarize_gate_status(
        signals,
        backtest_metrics=backtest["metrics"],
        market_regime=market_regime,
    )
    shadow_portfolio = build_shadow_portfolio(
        market_data,
        top_n=top_n,
        lookback_days=shadow_days,
    )
    universe_hash = build_universe_hash(tradable_universe["ts_code"].astype(str))
    snapshot = create_snapshot(
        trading_date=format_api_date(market_data.trade_date),
        data_version=market_data.data_version,
        universe_hash=universe_hash,
        source=market_data.source,
        mock_mode=market_data.mock_mode,
        results={
            "picks": results,
            "candidate_pools": candidate_pools,
            "score_profile": _score_profile(),
            "portfolio": portfolio_result["positions"],
            "signals": signals,
            "signal_summary": signal_summary,
            "gate_summary": gate_summary,
            "risk": portfolio_result["risk"],
            "portfolio_mode": portfolio_mode,
            "market_regime": market_regime,
            "risk_budget": risk_budget,
            "correlation_risk": correlation_risk,
            "factor_health": factor_health,
            "concentration_risk": concentration_risk,
            "portfolio_stability": portfolio_stability,
            "backtest": {
                "metrics": backtest["metrics"],
                "assumptions": backtest["assumptions"],
            },
            "shadow_portfolio": {
                "summary": shadow_portfolio.get("summary", {}),
                "metrics": shadow_portfolio.get("metrics", {}),
                "assumptions": shadow_portfolio.get("assumptions", {}),
            },
        },
        persist=save_snapshot,
    )

    return {
        "status": "ok",
        "date": format_api_date(market_data.trade_date),
        "trading_date": format_api_date(market_data.trade_date),
        "source": market_data.source,
        "mock_mode": market_data.mock_mode,
        "data_version": market_data.data_version,
        **snapshot,
        "market_features": market_features,
        "market_regime": market_regime,
        "risk_budget": risk_budget,
        "portfolio_mode": portfolio_mode,
        "correlation_risk": correlation_risk,
        "factor_health": factor_health,
        "concentration_risk": concentration_risk,
        "portfolio_stability": portfolio_stability,
        "signals": signals,
        "signal_summary": signal_summary,
        "gate_summary": gate_summary,
        "shadow_portfolio": shadow_portfolio,
        "backtest": backtest,
        "universe_size": int(len(tradable_universe)),
        "portfolio": portfolio_result["positions"],
        "risk": portfolio_result["risk"],
        "candidate_pools": candidate_pools,
        "score_profile": _score_profile(),
        "data": results,
    }


def _build_candidate_pools(scored: pd.DataFrame, top_n: int) -> dict[str, list[dict[str, Any]]]:
    limit = max(min(top_n, 10), 0)
    pools = {
        "value": ("value_candidate_score", "value"),
        "growth": ("growth_candidate_score", "growth"),
        "trend": ("trend_candidate_score", "trend"),
    }
    result: dict[str, list[dict[str, Any]]] = {}
    for name, (score_column, style) in pools.items():
        if scored.empty or score_column not in scored.columns:
            result[name] = []
            continue
        sort_columns = [score_column, "industry_strength", "final_score", "ts_code"]
        sort_orders = [False, False, False, True]
        if name == "growth":
            sort_columns = [
                score_column,
                "growth_theme_profile",
                "growth_industry_profile",
                "growth_data_quality",
                "final_score",
                "ts_code",
            ]
            sort_orders = [False, False, False, False, False, True]
        ranked = scored.sort_values(sort_columns, ascending=sort_orders).head(limit)
        result[name] = [
            _to_pick(row, candidate_style=style, candidate_score_column=score_column)
            for _, row in ranked.iterrows()
        ]
    return result


def _score_profile() -> dict[str, Any]:
    return {
        "mode": "growth_trend",
        "weights": GROWTH_TREND_WEIGHTS,
        "notes": {
            "value": "估值权重从 0.20 降至 0.08",
            "risk": "低波动风险权重从 0.20 降至 0.10",
            "trend": "趋势使用 20/60/120 日强度、创新高距离和成交额放大",
            "growth": "成长使用营收增速、利润增速、ROE、ROE 改善和成交额放大",
            "growth_theme_profile": "成长候选增加题材画像，优先 AI算力、芯片半导体、机器人、高端制造、新能源智能车等方向",
            "growth_industry_profile": "成长候选保留行业画像，金融行业在成长数据缺失时降权",
            "industry_strength": "行业相对强弱进入总分，降低弱势老行业仅靠便宜估值反复霸榜的概率",
        },
    }
