import os
import warnings

os.environ["MYINVESTPICKING_FORCE_MOCK"] = "1"

import pandas as pd
from starlette.exceptions import StarletteDeprecationWarning

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=StarletteDeprecationWarning,
)

from fastapi.testclient import TestClient

from app.main import app
from engine.scoring import score_stocks
from engine.signal_gate import build_signal_decision
from engine.theme_engine import add_growth_theme_profiles
from engine.tradability_engine import assess_tradability
from risk.portfolio_builder import build_portfolio


client = TestClient(app)


def test_growth_candidate_penalizes_financials_when_growth_data_missing() -> None:
    frame = [
        {
            "ts_code": "600001.SH",
            "industry": "银行",
            "momentum_20d": 0.08,
            "momentum_60d": 0.18,
            "momentum_120d": 0.28,
            "amount_expansion_20d": 2.0,
            "high_120_distance": -0.01,
            "volatility_20d": 0.02,
            "growth_data_quality": 0.0,
            "industry_relative_strength": 0.9,
            "pe": 6,
            "pb": 0.8,
        },
        {
            "ts_code": "688001.SH",
            "industry": "半导体",
            "momentum_20d": 0.07,
            "momentum_60d": 0.16,
            "momentum_120d": 0.25,
            "amount_expansion_20d": 1.8,
            "high_120_distance": -0.02,
            "volatility_20d": 0.03,
            "growth_data_quality": 0.0,
            "industry_relative_strength": 0.8,
            "pe": 35,
            "pb": 4.2,
        },
    ]

    scored = score_stocks(pd.DataFrame(frame))
    bank = scored.loc[scored["ts_code"] == "600001.SH"].iloc[0]
    semiconductor = scored.loc[scored["ts_code"] == "688001.SH"].iloc[0]

    assert semiconductor["growth_industry_profile"] > bank["growth_industry_profile"]
    assert semiconductor["growth_candidate_score"] > bank["growth_candidate_score"]


def test_growth_theme_profile_promotes_ai_theme_over_financials() -> None:
    frame = pd.DataFrame(
        [
            {
                "ts_code": "600001.SH",
                "industry": "银行",
                "momentum_20d": 0.08,
                "momentum_60d": 0.18,
                "momentum_120d": 0.28,
                "amount_expansion_20d": 2.0,
                "high_120_distance": -0.01,
                "volatility_20d": 0.02,
                "growth_data_quality": 0.0,
                "growth_theme_profile": 0.25,
                "industry_relative_strength": 0.9,
                "pe": 6,
                "pb": 0.8,
            },
            {
                "ts_code": "688001.SH",
                "industry": "通信设备",
                "momentum_20d": 0.07,
                "momentum_60d": 0.16,
                "momentum_120d": 0.25,
                "amount_expansion_20d": 1.8,
                "high_120_distance": -0.02,
                "volatility_20d": 0.03,
                "growth_data_quality": 0.0,
                "growth_theme_profile": 0.98,
                "industry_relative_strength": 0.8,
                "pe": 35,
                "pb": 4.2,
            },
        ]
    )

    scored = score_stocks(frame)
    bank = scored.loc[scored["ts_code"] == "600001.SH"].iloc[0]
    ai_stock = scored.loc[scored["ts_code"] == "688001.SH"].iloc[0]

    assert ai_stock["growth_theme_profile"] > bank["growth_theme_profile"]
    assert ai_stock["growth_candidate_score"] > bank["growth_candidate_score"]


def test_growth_theme_profiles_merge_external_theme_membership() -> None:
    factors = pd.DataFrame(
        [
            {"ts_code": "688001.SH", "name": "测试科技", "industry": "通信设备"},
            {"ts_code": "600001.SH", "name": "测试银行", "industry": "银行"},
        ]
    )
    membership = pd.DataFrame(
        [
            {
                "ts_code": "688001.SH",
                "theme_name": "人工智能算力",
                "theme_group": "AI算力",
                "theme_source": "tushare_ths",
            }
        ]
    )

    enriched = add_growth_theme_profiles(factors, membership)
    ai_stock = enriched.loc[enriched["ts_code"] == "688001.SH"].iloc[0]
    bank = enriched.loc[enriched["ts_code"] == "600001.SH"].iloc[0]

    assert ai_stock["theme_tags"] == "AI算力"
    assert ai_stock["theme_source"] == "tushare"
    assert ai_stock["growth_theme_profile"] > bank["growth_theme_profile"]


def test_index_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "MyInvestPicking" in response.text
    assert '<div data-myinvest-header></div>' in response.text
    assert '<div data-myinvest-footer></div>' in response.text
    assert 'src="https://invest.okbbc.com/header.js"' in response.text
    assert 'src="https://invest.okbbc.com/footer.js"' in response.text
    assert '<header class="page-header">' in response.text
    assert "候选榜" in response.text
    assert "价值候选" in response.text
    assert "成长候选" in response.text
    assert "趋势候选" in response.text
    assert "目标组合" in response.text
    assert "调仓规则" in response.text
    assert "影子组合" in response.text
    assert "接口说明" in response.text
    assert 'id="api-status"' in response.text
    assert "<th>仓位</th>" in response.text
    assert "https://xueqiu.com/S/" in response.text
    assert "https://stock.okbbc.com/research?stock=" in response.text


def test_api_catalog_returns_public_endpoint_directory() -> None:
    response = client.get("/api")
    assert response.status_code == 200

    payload = response.json()
    assert payload["system"]["name"] == "MyInvestPicking"
    assert payload["system"]["version"]
    assert payload["base_url"] == "http://testserver"
    assert payload["docs"] == {
        "swagger": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
    }
    assert payload["recommended_entrypoints"]
    assert payload["safety"]["catalog"].startswith("GET /api")
    assert "交易" in payload["safety"]["trading"] or "交易" in payload["safety"]["catalog"]
    assert payload["groups"]

    endpoints = [
        endpoint
        for group in payload["groups"]
        for endpoint in group["endpoints"]
    ]
    unique_paths = {(endpoint["method"], endpoint["path"]) for endpoint in endpoints}
    assert payload["total_endpoints"] == len(unique_paths)
    assert ("GET", "/api") in unique_paths
    assert ("GET", "/api/picks") in unique_paths
    assert ("GET", "/api/shadow-portfolio") in unique_paths
    catalog = next(endpoint for endpoint in endpoints if endpoint["path"] == "/api")
    assert catalog["read_only"] is True
    assert {"method", "path", "purpose", "parameters", "returns", "read_only"} <= set(
        catalog
    )


def test_picks_endpoint_returns_structured_results() -> None:
    response = client.get("/api/picks?top_n=5")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["source"] == "mock"
    assert payload["mock_mode"] is True
    assert payload["data_version"]
    assert payload["factor_version"] == "v3"
    assert payload["snapshot_id"]
    assert payload["universe_hash"]
    assert len(payload["data"]) == 5
    assert len(payload["portfolio"]) == 5
    assert len(payload["signals"]) == 5
    assert payload["signal_summary"]["counts"]
    assert payload["market_regime"]["state"] == "ignored"
    assert 0 <= payload["market_regime"]["confidence"] <= 1
    assert payload["portfolio_mode"]["name"] == "full_invested_shadow_portfolio"
    assert payload["portfolio_mode"]["market_factors_used_for_exposure"] is False
    assert payload["risk_budget"]["max_position_per_stock"] > 0
    assert payload["risk_budget"]["target_exposure"] == 1.0
    assert payload["risk"]["max_position_per_stock"] == payload["risk_budget"][
        "max_position_per_stock"
    ]
    assert payload["risk"]["portfolio_exposure"] <= payload["risk_budget"]["target_exposure"]
    assert payload["risk"]["max_beijing_weight"] == payload["risk_budget"]["max_beijing_weight"]
    assert payload["risk"]["exchange_exposure"].get("BJ", 0) <= payload["risk_budget"][
        "max_beijing_weight"
    ]
    assert "correlation_risk" in payload
    assert "factor_health" in payload
    assert "concentration_risk" in payload
    assert "portfolio_stability" in payload
    assert "backtest" in payload
    assert "gate_summary" in payload
    assert "candidate_pools" in payload
    assert "score_profile" in payload
    assert "shadow_portfolio" in payload
    assert 0 <= payload["factor_health"]["factor_health_score"] <= 1.05
    assert 0 <= payload["portfolio_stability"]["stability_score"] <= 1
    assert {"cagr", "sharpe", "max_drawdown", "turnover", "win_rate"} <= set(
        payload["backtest"]["metrics"]
    )
    assert payload["backtest"]["equity_curve"]
    assert payload["backtest"]["drawdown_curve"]
    assert payload["shadow_portfolio"]["status"] == "ok"
    assert payload["shadow_portfolio"]["assumptions"]["ratio_only"] is True
    assert payload["score_profile"]["mode"] == "growth_trend"
    assert payload["score_profile"]["weights"]["value"] == 0.08
    assert payload["score_profile"]["weights"]["risk"] == 0.10
    assert {"value", "growth", "trend"} <= set(payload["candidate_pools"])
    assert all(payload["candidate_pools"][key] for key in ["value", "growth", "trend"])
    assert payload["signal_summary"]["operation_counts"]
    assert payload["gate_summary"]["backtest_gate"]["state"] == "observed"
    assert payload["shadow_portfolio"]["equity_curve"]
    assert payload["shadow_portfolio"]["rebalance_history"]
    assert payload["shadow_portfolio"]["summary"]["latest_exposure"] == 1.0
    assert payload["shadow_portfolio"]["assumptions"]["target_exposure"] == 1.0
    assert {
        "start_nav",
        "end_nav",
        "total_return",
        "rebalance_count",
        "latest_exposure",
    } <= set(payload["shadow_portfolio"]["summary"])

    first = payload["data"][0]
    assert {"code", "score", "final_score", "factors", "metrics", "contribution", "reason"} <= set(
        first
    )
    assert {
        "momentum",
        "trend",
        "growth",
        "growth_data_quality",
        "quality",
        "value",
        "risk",
        "industry_strength",
        "growth_industry_profile",
        "growth_theme_profile",
    } <= set(first["factors"])
    assert {"revenue_growth_yoy", "net_profit_growth_yoy", "ocf_to_profit"} <= set(
        first["metrics"]
    )
    assert {
        "momentum_60d",
        "momentum_120d",
        "amount_expansion_20d",
        "high_120_distance",
        "roe_improvement",
        "growth_data_quality",
        "growth_industry_profile",
        "growth_theme_profile",
        "theme_tags",
        "theme_source",
        "industry_relative_strength",
    } <= set(first["metrics"])
    assert {"value", "growth", "trend", "composite"} <= set(first["candidate_scores"])
    assert first["candidate_style"] == "composite"
    assert "factor_health_score" in first
    assert "exchange_risk_multiplier" in first
    assert "liquidity_risk_multiplier" in first

    first_position = payload["portfolio"][0]
    assert {"code", "weight", "score", "final_score"} <= set(first_position)
    assert first_position["weight"] <= payload["risk_budget"]["max_position_per_stock"]
    assert max(payload["risk"]["industry_exposure"].values()) <= payload["risk_budget"][
        "max_industry_weight"
    ]

    first_signal = payload["signals"][0]
    assert {
        "code",
        "action",
        "confidence",
        "position_size",
        "operation_state",
        "position_policy",
        "gate_reasons",
        "tradability",
        "signal_confidence",
        "reason",
    } <= set(first_signal)
    assert first_signal["action"] in {"BUY", "HOLD", "NO_TRADE"}
    assert first_signal["operation_state"] in {"buyable", "watch", "risk_blocked", "research"}
    assert 0 <= first_signal["confidence"] <= 1


def test_picks_endpoint_is_deterministic_for_same_input() -> None:
    first = client.get("/api/picks?date=2026-06-24&top_n=5").json()
    second = client.get("/api/picks?date=2026-06-24&top_n=5").json()

    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["data_version"] == second["data_version"]
    assert first["data"] == second["data"]
    assert first["portfolio"] == second["portfolio"]
    assert first["signals"] == second["signals"]
    assert first["signal_summary"] == second["signal_summary"]
    assert first["risk"] == second["risk"]
    assert first["market_regime"] == second["market_regime"]
    assert first["risk_budget"] == second["risk_budget"]
    assert first["correlation_risk"] == second["correlation_risk"]
    assert first["factor_health"] == second["factor_health"]
    assert first["portfolio_stability"] == second["portfolio_stability"]
    assert first["backtest"] == second["backtest"]
    assert first["gate_summary"] == second["gate_summary"]
    assert first["candidate_pools"] == second["candidate_pools"]
    assert first["score_profile"] == second["score_profile"]
    assert first["shadow_portfolio"] == second["shadow_portfolio"]


def test_backtest_reduce_allows_probe_sized_high_conviction_buy() -> None:
    decision = build_signal_decision(
        position={
            "code": "600001.SH",
            "name": "Test",
            "final_score": 0.7,
            "weight": 0.1,
        },
        tradability={"tradable": True, "reasons": []},
        confidence={"confidence": 0.86, "components": {}},
        market_regime={"state": "range", "confidence": 0.6},
        correlation_context={"cluster_block": False},
        backtest_context={
            "block_buy": False,
            "reduce_buy": True,
            "caution": True,
            "state": "reduced",
            "sharpe": -2.0,
            "max_drawdown": -0.0993,
        },
    )

    assert decision["action"] == "BUY"
    assert decision["operation_state"] == "buyable"
    assert decision["position_policy"] == "probe_only"
    assert decision["position_size"] == 0.025
    assert "backtest_reduce" in decision["gate_reasons"]


def test_shadow_portfolio_endpoint_returns_history() -> None:
    response = client.get("/api/shadow-portfolio?top_n=5&shadow_days=3")
    assert response.status_code == 200

    payload = response.json()
    shadow = payload["shadow_portfolio"]
    assert payload["status"] == "ok"
    assert payload["source"] == "mock"
    assert payload["mock_mode"] is True
    assert shadow["status"] == "ok"
    assert shadow["assumptions"]["ratio_only"] is True
    assert len(shadow["equity_curve"]) == 4
    assert len(shadow["rebalance_history"]) == 3
    assert shadow["summary"]["latest_exposure"] == 1.0
    first_rebalance = shadow["rebalance_history"][0]
    assert {"rebalance_date", "applied_date", "nav", "target_exposure", "changes"} <= set(
        first_rebalance
    )


def test_portfolio_caps_beijing_exchange_exposure() -> None:
    picks = [
        {"code": "920001.BJ", "final_score": 0.9, "industry": "A"},
        {"code": "920002.BJ", "final_score": 0.8, "industry": "B"},
        {"code": "600001.SH", "final_score": 0.7, "industry": "C"},
        {"code": "000001.SZ", "final_score": 0.6, "industry": "D"},
    ]

    result = build_portfolio(
        picks,
        max_position_per_stock=0.6,
        max_industry_weight=0.8,
        target_exposure=1.0,
        max_beijing_weight=0.15,
    )

    assert result["risk"]["exchange_exposure"]["BJ"] <= 0.15


def test_tradability_blocks_untradeable_candidates() -> None:
    position = {
        "code": "600001.SH",
        "name": "Test",
        "metrics": {
            "latest_pct_chg": 9.9,
            "latest_amount": 10_000,
            "turnover_rate": 0.2,
            "volatility_20d": 0.08,
        },
    }

    result = assess_tradability(position)

    assert result["tradable"] is False
    assert "near limit up" in result["reasons"]
    assert "low latest amount" in result["reasons"]
    assert "low turnover" in result["reasons"]
