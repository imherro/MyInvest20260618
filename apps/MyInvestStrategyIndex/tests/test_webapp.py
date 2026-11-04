from __future__ import annotations

import json

from myinvest_strategy_index.config import load_settings
from myinvest_strategy_index.webapp import (
    render_cashflow_growth_compare_page,
    render_chinext_compare_page,
    render_four_asset_compare_page,
    render_home_page,
    render_strategy_backtest_detail_page,
    render_strategy_backtests_page,
    render_strategy_index_compare_page,
    render_three_asset_compare_page,
    render_us_etf_compare_page,
    render_inflation_portfolio_page,
    render_us_etf_strategy_observer_page,
    render_value_compare_page,
)


def test_home_page_renders_strategy_card_entry() -> None:
    html = render_home_page()

    assert "策略入口 - MyInvestStrategyIndex" in html
    assert "策略研究" in html
    assert "策略回测" in html
    assert 'href="/value-compare"' in html
    assert 'href="/chinext-compare"' in html
    assert 'href="/four-asset-compare"' in html
    assert 'href="/three-asset-compare"' in html
    assert 'href="/cashflow-growth-compare"' in html
    assert 'href="/us-etf-compare"' in html
    assert 'href="/us-inflation-portfolio"' in html
    assert 'href="/us-etf-strategy-observer"' in html
    assert 'href="/strategy-backtests"' in html
    assert "策略指数收益曲线对比" in html
    assert "value-compare" in html
    assert "创业板全收益指数对比" in html
    assert "chinext-compare" in html
    assert "四资产组合对比" in html
    assert "four-asset" in html
    assert "三资产组合对比" in html
    assert "three-asset" in html
    assert "自由现金流R与创成长R对比" in html
    assert "cashflow-growth" in html
    assert "美股 ETF 组合对比" in html
    assert "us-etf" in html
    assert "Cycle 策略回测集合" in html
    assert "strategy-backtests" in html
    assert "/api/strategy-index-compare/history.json" not in html
    assert "/api/chinext-compare/history.json" not in html
    assert "/api/four-asset-compare/history.json" not in html
    assert "/api/three-asset-compare/history.json" not in html
    assert "/api/cashflow-growth-compare/history.json" not in html
    assert "/api/us-etf-compare/history.json" not in html


def test_us_etf_compare_page_renders_six_fund_equal_weight_shell() -> None:
    html = render_us_etf_compare_page()
    assert "美股 ETF 组合对比" in html
    assert "/api/us-etf-compare/history.json" in html
    assert 'data-synthetic-code="VIRTUAL_US_ETF_EQUAL_WEIGHT"' in html
    assert 'data-show-background="false"' in html
    assert "RSP、IWY、MOAT、SPMO" in html
    assert "PFF" in html and "VNQ" in html
    assert "每只目标权重 16.67%" in html
    assert "最长回本时间" in html


def test_inflation_portfolio_page_renders_strategy_and_audit_metrics() -> None:
    html = render_inflation_portfolio_page()
    assert "美股抗通胀组合策略" in html
    assert "/api/us-inflation-portfolio/history.json" in html
    assert 'data-synthetic-code="VIRTUAL_INFLATION_EQUAL_WEIGHT"' in html
    assert "SPMO 30%、MOAT 20%、IEF 20%、IAU 15%、KMLM 10%、PDBC 5%" in html
    assert "季度末检查" in html and "10bp" in html
    assert "六资产等权曲线" in html and "每只 16.67%" in html
    assert 'id="portfolio-analysis-section"' in html
    assert "renderPortfolioAnalysis" in html
    assert "Sortino" in html
    assert "滚动36个月最差年化收益" in html
    assert "risk_contributions" in html
    assert "correlation_matrix" in html
    assert "annual_turnover" in html


def test_us_etf_strategy_observer_page_prioritizes_calmar_and_dynamic_equal_weight() -> None:
    html = render_us_etf_strategy_observer_page()
    assert "美股 ETF 策略观察池" in html
    assert "/api/us-etf-strategy-observer/history.json" in html
    assert 'data-synthetic-code="VIRTUAL_US_ETF_OBSERVER_EQUAL_WEIGHT"' in html
    assert "核心 Beta" in html and "风险/风格增强器" in html
    assert "防御或避险组件" in html and "策略类" in html
    assert "SPY 标普500ETF" not in html and "ITOT 美国全市场ETF" not in html
    default_unselected = html.split('data-default-unselected-codes="', 1)[1].split('"', 1)[0].split(",")
    assert "VOO" not in default_unselected
    assert "VIRTUAL_US_ETF_OBSERVER_EQUAL_WEIGHT" not in default_unselected
    assert len(default_unselected) == 28
    assert {"RSP", "IWY", "MOAT", "SPMO", "PFF", "VNQ", "IEF", "IAU", "KMLM", "PDBC"} <= set(default_unselected)
    assert "取消或增加真实 ETF 后，立即按当前选择重新等权计算" in html
    assert '<th data-sort="annualizedReturnDrawdownRatio" class="sorted-desc">Calmar</th>' in html
    assert "toggleInstrumentCategory" in html


def test_value_compare_page_renders_strategy_index_shell() -> None:
    html = render_strategy_index_compare_page()

    assert render_value_compare_page() == html
    assert "策略指数收益曲线对比" in html
    assert "/api/strategy-index-compare/history.json" in html
    assert 'data-extra-metrics="true"' in html
    assert 'data-synthetic-code="VIRTUAL_EQUAL_WEIGHT_STRATEGY"' in html
    assert 'data-risk-parity-code="VIRTUAL_RISK_PARITY_STRATEGY"' in html
    assert "data-default-unselected-codes" not in html
    assert 'data-anchor-synthetic="false"' in html
    assert 'data-show-background="true"' in html
    assert 'const state = {' in html
    assert 'dynamicSyntheticRows: []' in html
    assert 'dynamicRiskParityRows: []' in html
    assert 'dynamicDrawdownRiskRows: []' in html
    assert 'rangeMode: "common"' in html
    assert 'sortKey: "annualizedReturnDrawdownRatio"' in html
    assert '<button id="mode-longest" type="button" class="secondary" data-mode="longest">最早起</button>' in html
    assert '<button id="mode-common" type="button" data-mode="common">共同区间</button>' in html
    assert '<th data-sort="annualizedReturn">年化收益</th>' in html
    assert '<th data-sort="annualizedReturnDrawdownRatio" class="sorted-desc">年化收益/最大回撤</th>' in html
    assert 'href="/"' in html
    assert "国信价值全收益" in html
    assert "创成长R" in html
    assert "价值100R" not in html
    assert "自由现金流R" in html
    assert "华安黄金ETF" in html
    assert "十年国债ETF" in html
    assert "分层权重模型" in html
    assert "Calmar 优化结论" in html
    assert "国信价值0%、创成长R11.13%、红利低波0%、自由现金流R25.22%、黄金ETF23.64%、十年国债ETF40.00%" in html
    assert "最优分层权重模型年化表现" in html
    assert "年化收益 12.73%，年化波动 8.86%，最大回撤 7.44%，Sharpe 1.453，Calmar 1.713" in html
    assert "样本内有效、样本外不稳健" in html
    assert "样本外 Calmar 0.874" in html
    assert "70/30 样本外验证" in html
    assert 'instrument.kind === "index"' not in html
    assert "isDynamicSyntheticCode" in html
    assert "策略等权组合" in html
    assert "风险平价组合" in html
    assert "buildRiskParityRows" in html
    assert "inverseVolatilityWeights" in html
    assert "dynamicRiskParityRows" in html
    assert 'id="risk-parity-weights"' in html
    assert "renderRiskParityWeights" in html
    assert "风险平价最新比例" in html
    assert "上证指数作为灰色背景线" in html
    assert "background_series" in html
    assert "backgroundNormalizedSeries" in html
    assert "background-line" in html
    assert 'data-show-index-relationships="true"' in html
    assert "指数成分重叠与相关性" in html
    assert "renderIndexRelationships" in html
    assert "日收益相关性" in html
    assert "成分权重重叠" in html
    assert "最长回本时间" in html
    assert 'class="control-group time-controls"' in html
    assert "ETF选择" in html
    assert 'class="chart-toolbar"' in html
    assert 'id="chart-tooltip"' in html
    assert 'id="interaction-select"' in html
    assert "showChartCrosshair" in html
    assert "drawRangeSelection" in html
    assert 'setInteractionMode("select")' in html


def test_chinext_compare_page_renders_three_total_return_indices() -> None:
    html = render_chinext_compare_page()

    assert "创业板全收益指数对比" in html
    assert "/api/chinext-compare/history.json" in html
    assert 'data-extra-metrics="true"' in html
    assert 'data-anchor-synthetic="false"' in html
    assert 'data-show-background="false"' in html
    assert 'href="/"' in html
    assert 'href="/value-compare"' in html
    assert "399006 创业板指" in html
    assert "399673 创业板50" in html
    assert "399296 创成长" in html
    assert "399606.SZ、CN2673.CNI、CN2296.CNI" in html
    assert "Calmar 优化结论" not in html
    assert "样本内有效、样本外不稳健" not in html
    assert "最长回本时间" in html


def test_cashflow_growth_compare_page_renders_two_index_shell() -> None:
    html = render_cashflow_growth_compare_page()

    assert "自由现金流R与创成长R对比" in html
    assert "/api/cashflow-growth-compare/history.json" in html
    assert 'data-extra-metrics="true"' in html
    assert 'data-synthetic-code="VIRTUAL_CASHFLOW_GROWTH_EQUAL_WEIGHT"' in html
    assert 'data-risk-parity-code="VIRTUAL_CASHFLOW_GROWTH_RISK_PARITY"' in html
    assert 'data-drawdown-risk-code="VIRTUAL_CASHFLOW_GROWTH_DRAWDOWN_RISK"' in html
    assert 'data-anchor-synthetic="false"' in html
    assert 'data-show-background="true"' in html
    assert 'href="/"' in html
    assert 'href="/value-compare"' in html
    assert "480092.CNI 自由现金流R、CN2296.CNI 创成长R" in html
    assert "双指数等权组合" in html
    assert "滚动60日风险平价组合" in html
    assert "过去10年逆最大回撤风险平价组合" in html
    assert "最大回撤风险平价最优再平衡组合" in html
    assert "再平衡测试结论" in html
    assert 'id="rebalance-analysis-section"' in html
    assert "renderRebalanceAnalysis" in html
    assert "best_rule_name" in html
    assert "最大回撤风险平价比例" in html
    assert "inverseDrawdownWeights" in html
    assert "dynamicDrawdownRiskRows" in html
    assert 'id="risk-parity-weights"' in html
    assert "风险平价最新比例" in html
    assert "latest.weights" in html
    assert "上证指数作为灰色背景线" in html
    assert "Calmar 优化结论" not in html
    assert "国信价值全收益" not in html
    assert "红利低波全收益" not in html
    assert "华安黄金ETF" not in html
    assert "十年国债ETF" not in html
    assert "最长回本时间" in html


def test_four_asset_compare_page_renders_calmar_layered_model() -> None:
    html = render_four_asset_compare_page()

    assert "四资产组合对比" in html
    assert "/api/four-asset-compare/history.json" in html
    assert 'data-extra-metrics="true"' in html
    assert 'data-synthetic-code="VIRTUAL_FOUR_ASSET_EQUAL_WEIGHT"' in html
    assert 'data-anchor-synthetic="false"' in html
    assert 'data-show-background="false"' in html
    assert 'href="/"' in html
    assert 'href="/value-compare"' in html
    assert "四资产 Calmar 优化结论" in html
    assert "创业板R15.80%、自由现金流R18.45%、黄金ETF25.74%、十年国债ETF40.00%" in html
    assert "年化收益 10.43%，年化波动 8.54%，最大回撤 8.05%，Sharpe 1.251，Calmar 1.296" in html
    assert "等权组合年化收益 11.93%" in html
    assert "四资产等权组合" in html
    assert "分层权重模型" in html
    assert "最长回本时间" in html


def test_three_asset_compare_page_renders_calmar_layered_model() -> None:
    html = render_three_asset_compare_page()

    assert "三资产组合对比" in html
    assert "/api/three-asset-compare/history.json" in html
    assert 'data-extra-metrics="true"' in html
    assert 'data-synthetic-code="VIRTUAL_THREE_ASSET_EQUAL_WEIGHT"' in html
    assert 'data-anchor-synthetic="false"' in html
    assert 'data-show-background="false"' in html
    assert 'data-default-start-date="2017-08-24"' in html
    assert 'href="/"' in html
    assert 'href="/value-compare"' in html
    assert "三资产 Calmar 优化结论" in html
    assert "创业板R21.68%、自由现金流R38.32%、黄金ETF40.00%" in html
    assert "年化收益 14.75%，年化波动 14.38%，最大回撤 15.84%，Sharpe 1.067，Calmar 0.931" in html
    assert "等权组合年化收益 14.39%" in html
    assert "三资产等权组合" in html
    assert "分层权重模型" in html
    assert "最长回本时间" in html


def test_strategy_backtests_page_renders_cycle_result_cards(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    backtest_dir = tmp_path / "cycle" / "strategy_backtests"
    backtest_dir.mkdir(parents=True)
    _write_backtest(backtest_dir / "four-asset.json", strategy_id="four-asset")

    html = render_strategy_backtests_page(settings, backtest_dir=backtest_dir)

    assert "策略回测 - MyInvestStrategyIndex" in html
    assert "Cycle 子系统回测集合" in html
    assert "资产配置（1）" in html
    assert 'href="/strategy-backtests/four-asset"' in html
    assert "four-asset strategy" in html
    assert "/api/strategy-backtests/index.json" in html


def test_strategy_backtest_detail_page_renders_cycle_result(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    backtest_dir = tmp_path / "cycle" / "strategy_backtests"
    backtest_dir.mkdir(parents=True)
    _write_backtest(backtest_dir / "four-asset.json", strategy_id="four-asset")

    html = render_strategy_backtest_detail_page(settings, "four-asset", backtest_dir=backtest_dir)

    assert "four-asset strategy - 策略回测" in html
    assert "回测摘要" in html
    assert "年化收益" in html
    assert "20.00%" in html
    assert "最大回撤" in html
    assert "-10.00%" in html
    assert "净值曲线" in html
    assert "510300.SH" in html
    assert "/api/strategy-backtests/four-asset.json" in html


def _write_backtest(path, *, strategy_id: str) -> None:
    payload = {
        "metadata": {
            "strategy_id": strategy_id,
            "description": "sample strategy",
            "method": ["sample method"],
        },
        "summary": {
            "strategy_id": strategy_id,
            "strategy_name": f"{strategy_id} strategy",
            "short_name": strategy_id,
            "start_date": "20200102",
            "end_date": "20210104",
            "sessions": 252,
            "rebalance_count": 3,
            "strategy_total_return": 0.2,
            "max_drawdown": -0.1,
            "sharpe": 1.2,
            "latest_signal": "sample_signal",
            "latest_signal_date": "20210104",
            "latest_weights": {"510300.SH": 0.6, "511880.SH": 0.4},
            "comparison_assets": [
                {
                    "code": "equal_weight",
                    "annualized_return": 0.1,
                    "max_drawdown": -0.12,
                    "sharpe": 0.8,
                    "calmar": 0.83,
                }
            ],
        },
        "equity_curve": [
            {"date": "20200102", "strategy_equity": 1.0, "equal_weight_equity": 1.0},
            {"date": "20210104", "strategy_equity": 1.2, "equal_weight_equity": 1.1},
        ],
        "signals": [{"date": "20210104", "signal": "buy", "target_weights": {"510300.SH": 0.6}}],
        "validation": {"no_lookahead_bias": True},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
