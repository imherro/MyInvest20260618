from __future__ import annotations

import json

from tenbagger.web_app import (
    _build_api_catalog,
    _page,
    _render_backtest_section,
    _render_dashboard,
    _render_factor_section,
    _render_regime_section,
    _render_screener_section,
    create_app,
    _stock_code_link,
    _xueqiu_symbol,
)


def test_page_embeds_unified_myinvest_chrome() -> None:
    page = _page("<main class='shell'>content</main>")

    assert "data-myinvest-header" in page
    assert "data-myinvest-footer" in page
    assert "https://invest.okbbc.com/header.js" in page
    assert "https://invest.okbbc.com/footer.js" in page
    assert "https://invest.okbbc.com/api/header" in page
    assert "https://invest.okbbc.com/api/footer" in page


def test_xueqiu_symbol_converts_a_share_codes() -> None:
    assert _xueqiu_symbol("603259.SH") == "SH603259"
    assert _xueqiu_symbol("000001.SZ") == "SZ000001"
    assert _xueqiu_symbol("SH603259") == "SH603259"
    assert _xueqiu_symbol("S0") is None


def test_stock_code_link_uses_code_for_xueqiu_and_name_for_research() -> None:
    linked = _stock_code_link("603259.SH", "药明康德")

    assert ">603259.SH</a>" in linked
    assert 'href="https://xueqiu.com/S/SH603259"' in linked
    assert 'href="https://stock.okbbc.com/research?stock=603259.SH"' in linked
    assert 'target="_blank"' in linked
    assert 'rel="noopener noreferrer"' in linked
    assert ">药明康德</a>" in linked
    assert ">Xueqiu</a>" not in linked


def test_page_adds_chinese_hover_explanations() -> None:
    page = _page(
        """
        <main class="shell">
          <h1>TenBagger</h1>
          <section class="metrics"><div class="metric"><span>Stocks</span><strong>10</strong></div></section>
          <h2>Missing Rates</h2>
          <table>
            <thead><tr><th>ROE</th><th>RankIC</th></tr></thead>
            <tbody><tr><td>annual_return</td><td>0.1</td></tr></tbody>
          </table>
        </main>
        """
    )

    assert 'class="help"' in page
    assert "十倍股寻找系统" in page
    assert 'title="字段缺失率；越低说明基础数据越完整。"' in page
    assert 'title="净资产收益率，衡量公司赚钱效率。"' in page
    assert 'title="年化收益率；把区间收益换算成年维度。"' in page


def test_dashboard_shows_current_dataset_and_readable_counts() -> None:
    page = _render_dashboard(
        {
            "generated_at": "2026-06-25T12:25:41",
            "stock_count": 498,
            "row_count": 289526,
            "latest_trading_date": "2026-06-24",
            "date_range": {"start": "2024-01-08", "end": "2026-06-24"},
            "missing_rates": {},
            "stock_coverage": [],
            "latest_snapshot": [],
            "storage": {
                "source": "tushare",
                "universe": {"level": "research", "stock_count": 500},
            },
            "universe_level": "research",
            "universe_count": 500,
        },
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert "当前数据集：research 股票池" in page
    assert "目标 500 只" in page
    assert "已加载 498 只" in page
    assert "<strong>289,526</strong>" in page
    assert 'class="coverage-card"' in page
    assert 'class="table-scroll coverage-scroll"' in page
    assert "接口说明" in page
    assert "GET /api" in page


def test_empty_dashboard_still_shows_api_catalog() -> None:
    page = _render_dashboard(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert "TASK 1 report not found" in page
    assert "接口说明" in page
    assert "GET /api" in page


def test_api_catalog_lists_public_endpoints_and_safety() -> None:
    catalog = _build_api_catalog("http://127.0.0.1:8020")
    endpoints = [
        endpoint
        for group in catalog["groups"]
        for endpoint in group["endpoints"]
    ]

    assert catalog["system_name"] == "TenBagger"
    assert catalog["base_url"] == "http://127.0.0.1:8020"
    assert catalog["docs"]["swagger_ui"] == "/docs"
    assert catalog["total_endpoints"] == len(endpoints)
    assert {"文档入口", "当前数据", "历史数据", "分析结果", "系统状态"}.issubset(
        {group["name"] for group in catalog["groups"]}
    )
    assert any(endpoint["path"] == "/api" and endpoint["read_only"] for endpoint in endpoints)
    assert any(endpoint["path"] == "/api/task11/anomaly" for endpoint in endpoints)
    assert any(endpoint["path"] == "/api/universe/revaluation" and not endpoint["read_only"] for endpoint in endpoints)
    assert catalog["safety"]["catalog_read_only"] is True
    assert "交易" in catalog["safety"]["trading_boundary"]


def test_dashboard_defaults_to_v2_and_links_to_v1() -> None:
    backtest_report = {
        "date_range": {"start": "2024-01-01", "end": "2026-06-24"},
        "config": {"rebalance": "monthly"},
        "rebalance_count": 12,
        "final_nav": 1.0,
        "metrics": {},
        "factor_attribution": {},
        "latest_holdings": [{"ts_code": "603259.SH", "weight": 0.05, "rebalance_date": "2026-05-29"}],
    }
    page = _render_dashboard(
        {
            "generated_at": "2026-06-25T12:25:41",
            "stock_count": 1,
            "row_count": 10,
            "latest_trading_date": "2026-06-24",
            "date_range": {"start": "2024-01-08", "end": "2026-06-24"},
            "missing_rates": {},
            "stock_coverage": [],
            "latest_snapshot": [],
            "storage": {},
        },
        {"validation": {}, "latest_top_scores": [], "model_v2_summary": {}, "latest_top_scores_v2": []},
        {
            "candidate_count": 0,
            "backtest_preview": {},
            "ic_decay_curve": [],
            "top_candidates": [{"ts_code": "603259.SH", "tenbagger_score": 70.0}],
            "near_misses": [],
            "v2_backtest_preview": {},
            "v2_ic_decay_curve": [],
            "model_v2_summary": {},
            "v2_top_candidates": [],
        },
        backtest_report,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert "TenBagger Model V2" in page
    assert 'href="/model/v1"' in page
    assert "Model V2 Screener" in page
    assert "V1 Top Candidates" not in page
    assert "Portfolio Backtest" not in page
    assert "Latest Holdings" not in page

    v1_page = _render_dashboard(
        {
            "generated_at": "2026-06-25T12:25:41",
            "stock_count": 1,
            "row_count": 10,
            "latest_trading_date": "2026-06-24",
            "date_range": {"start": "2024-01-08", "end": "2026-06-24"},
            "missing_rates": {},
            "stock_coverage": [],
            "latest_snapshot": [],
            "storage": {},
        },
        {"validation": {}, "latest_top_scores": [], "model_v2_summary": {}, "latest_top_scores_v2": []},
        {
            "candidate_count": 0,
            "backtest_preview": {},
            "ic_decay_curve": [],
            "top_candidates": [{"ts_code": "603259.SH", "tenbagger_score": 70.0}],
            "near_misses": [],
            "v2_backtest_preview": {},
            "v2_ic_decay_curve": [],
            "model_v2_summary": {},
            "v2_top_candidates": [],
        },
        backtest_report,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        model_version="v1",
    )

    assert "Portfolio Backtest" in v1_page
    assert "Latest Holdings" in v1_page


def test_factor_and_screener_sections_show_model_v2() -> None:
    factor_section = _render_factor_section(
        {
            "validation": {"future_leak_rows": 0},
            "score_distribution": {
                "tenbagger_score_v2": {"std": 9.1, "min": 20.0, "max": 82.0},
            },
            "latest_top_scores": [],
            "model_v2_summary": {"eligible_count": 3, "latest_market_regime": "bull"},
            "latest_top_scores_v2": [
                {
                    "ts_code": "603259.SH",
                    "tenbagger_score": 70.0,
                    "tenbagger_score_v2": 82.0,
                    "v2_confidence_grade": "A",
                    "v2_eligible": True,
                    "v2_weight_profile": "growth",
                }
            ],
        },
        {"603259.SH": "药明康德"},
    )
    screener_section = _render_screener_section(
        {
            "candidate_count": 1,
            "backtest_preview": {},
            "ic_decay_curve": [],
            "top_candidates": [],
            "near_misses": [],
            "v2_backtest_preview": {"excess_return": 0.1},
            "v2_ic_decay_curve": [{"horizon_days": 21, "ic_mean": 0.02, "rank_ic_mean": 0.06, "observations": 10}],
            "model_v2_summary": {"candidate_count": 1, "eligible_rate": 0.5},
            "v2_top_candidates": [
                {
                    "ts_code": "603259.SH",
                    "tenbagger_score": 70.0,
                    "tenbagger_score_v2": 82.0,
                    "v2_confidence_grade": "A",
                    "v2_weight_profile": "growth",
                    "industry": "医药",
                    "v2_fail_reasons": "",
                }
            ],
        },
        {"603259.SH": "药明康德"},
    )

    assert "Model V2 Summary" in factor_section
    assert "Model V2 Validation" in factor_section
    assert "v2_score_std" in factor_section
    assert "Latest V2 Scores" in factor_section
    assert "V2 Candidates" in screener_section
    assert "V2 IC Decay" in screener_section
    assert "Latest V1 Factor Scores" not in factor_section
    assert "V1 Top Candidates" not in screener_section
    assert "<th>V1</th>" not in factor_section
    assert "<th>V1</th>" not in screener_section
    assert "82.0" in factor_section + screener_section


def test_v1_model_sections_are_separate() -> None:
    factor_section = _render_factor_section(
        {
            "validation": {"future_leak_rows": 0},
            "latest_top_scores": [
                {
                    "ts_code": "603259.SH",
                    "tenbagger_score": 70.0,
                    "growth_score": 80.0,
                    "quality_score": 75.0,
                    "value_score": 60.0,
                    "risk_score": 20.0,
                    "momentum_score": 66.0,
                }
            ],
            "model_v2_summary": {"eligible_count": 3},
            "latest_top_scores_v2": [{"ts_code": "603259.SH", "tenbagger_score_v2": 82.0}],
        },
        {"603259.SH": "药明康德"},
        model_version="v1",
    )
    screener_section = _render_screener_section(
        {
            "candidate_count": 1,
            "backtest_preview": {"excess_return": 0.1},
            "ic_decay_curve": [{"horizon_days": 21, "ic_mean": 0.02, "rank_ic_mean": 0.06, "observations": 10}],
            "top_candidates": [
                {
                    "ts_code": "603259.SH",
                    "tenbagger_score": 70.0,
                    "industry": "医药",
                    "revenue_growth_yoy": 0.2,
                    "roe": 0.1,
                    "debt_ratio": 0.3,
                    "fail_reasons": "",
                }
            ],
            "near_misses": [],
            "v2_backtest_preview": {"excess_return": 0.2},
            "v2_ic_decay_curve": [],
            "model_v2_summary": {"candidate_count": 1},
            "v2_top_candidates": [{"ts_code": "603259.SH", "tenbagger_score_v2": 82.0}],
        },
        {"603259.SH": "药明康德"},
        model_version="v1",
    )

    assert "Model V1 Factor Engine" in factor_section
    assert "Latest V1 Factor Scores" in factor_section
    assert "Latest V2 Scores" not in factor_section
    assert "Model V1 Screener" in screener_section
    assert "V1 Top Candidates" in screener_section
    assert "V2 Candidates" not in screener_section


def test_v1_route_requires_page_jump(tmp_path) -> None:
    (tmp_path / "task1_summary.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-25T12:25:41",
                "stock_count": 1,
                "row_count": 10,
                "latest_trading_date": "2026-06-24",
                "date_range": {"start": "2024-01-08", "end": "2026-06-24"},
                "missing_rates": {},
                "stock_coverage": [],
                "latest_snapshot": [],
                "storage": {},
            }
        ),
        encoding="utf-8",
    )
    app = create_app(tmp_path)
    paths = {route.path for route in app.routes}
    v1_page = _render_dashboard(
        json.loads((tmp_path / "task1_summary.json").read_text(encoding="utf-8")),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        model_version="v1",
    )

    assert "/" in paths
    assert "/api" in paths
    assert "/model/v1" in paths
    assert "TenBagger Model V1" in v1_page
    assert 'href="/">返回 Model V2</a>' in v1_page


def test_backtest_section_shows_period() -> None:
    section = _render_backtest_section(
        {
            "date_range": {"start": "2023-02-01", "end": "2026-06-24"},
            "config": {"rebalance": "monthly"},
            "rebalance_count": 41,
            "final_nav": 0.8106,
            "metrics": {},
            "factor_attribution": {"dominant_factor": "growth"},
            "latest_holdings": [],
        },
        {},
    )

    assert "Backtest Period: 2023-02-01 to 2026-06-24" in section
    assert "Rebalance: monthly" in section
    assert "Rebalances: 41" in section


def test_regime_history_clarifies_behavior_state() -> None:
    section = _render_regime_section(
        {
            "api_response": {
                "behavior_state": "transition",
                "trend_regime": "bull",
                "volatility_regime": "high",
                "liquidity_regime": "expansion",
            },
            "latest": {},
            "validation": {},
            "history": {"chart_tail": [{"date": "2026-06-24", "behavior_state": "transition"}]},
            "data_source": {"source": "local"},
        }
    )

    assert "Behavior State History" in section
    assert "不表示牛市早中晚阶段" in section
    assert "Regime History" not in section
