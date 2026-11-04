import json

import pandas as pd

from shortterm_trader.config import load_settings
from shortterm_trader.webapp import (
    _action_controls_html,
    _alert_table_html,
    _intraday_table_html,
    _position_snapshot_html,
    _qmt_snapshot_html,
    _realtime_coverage_symbols,
    _today_work_group_rows,
    _today_work_html,
    _today_work_rows,
    _watch_status_html,
    render_capital_migration_page,
    render_etf_compare_page,
    render_index_compare_page,
    render_strategy_index_compare_page,
    render_value_compare_page,
    render_dashboard,
    render_trend_channel_page,
    run_intraday_refresh_all_action,
    run_intraday_action,
    run_position_import_action,
    run_realtime_coverage_action,
)


def test_dashboard_renders_without_secret(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TUSHARE_TOKEN=secret-token\nFRED_API_KEY=secret-fred\n", encoding="utf-8")
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    settings = load_settings(root=tmp_path, env_file=env_file)
    html = render_dashboard(settings)
    assert "MyShortTerm" in html
    assert "明日计划" in html
    assert "本地行情库" in html
    assert "QMT 实时行情" in html
    assert "QMT 真实持仓" in html
    assert "今日处理清单" in html
    assert "研究频道" in html
    assert "channel-card" in html
    assert "ETF 对比" in html
    assert "/etf-compare" in html
    assert "指数对比" in html
    assert "/index-compare" in html
    assert "策略指数对比" in html
    assert "/strategy-index-compare" in html
    assert "宽基趋势图" in html
    assert "/broad-trend" in html
    assert "主线指数趋势图" in html
    assert "/theme-trend" in html
    assert "资金迁移雷达" in html
    assert "/capital-migration" in html
    assert "https://invest.okbbc.com/header.js" in html
    assert "https://invest.okbbc.com/footer.js" in html
    assert "data-myinvest-header" in html
    assert "data-myinvest-footer" in html
    assert "secret-token" not in html
    assert "secret-fred" not in html


def test_etf_compare_page_renders_interactive_shell() -> None:
    html = render_etf_compare_page()
    assert "ETF 复权价值曲线对比" in html
    assert "/api/etf-compare/history.json" in html
    assert "value-chart" in html
    assert "drawdown-chart" in html
    assert "bar-chart" in html
    assert "更新数据" in html
    assert "2012起" in html
    assert "共同区间" in html
    assert "Y轴" in html
    assert 'data-y-axis="return"' in html
    assert 'data-y-axis="multiple"' in html
    assert 'data-y-axis="log"' in html
    assert 'valueAxisMode: "return"' in html
    assert "累计收益率%" in html
    assert "净值倍数" in html
    assert "对数" in html
    assert "formatValueAxis" in html
    assert "valueAxisY" in html
    assert "480092 为自由现金流R收益指数点位代理" in html
    assert "980092" not in html
    for year in range(6, 11):
        assert f'data-years="{year}"' in html
        assert f"近{year}年" in html
    assert 'data-sort="annualizedReturn"' in html
    assert 'data-sort="annualizedReturnDrawdownRatio"' in html
    assert "年化收益/最大回撤" in html
    assert "fill: instrument.color" in html
    assert "最大回撤=曲线色" in html
    assert "buildDynamicSyntheticRows" in html
    assert "selectedComponentCodes" in html
    assert 'id="pan-left"' in html
    assert 'id="pan-right"' in html
    assert 'id="zoom-in"' in html
    assert 'id="zoom-out"' in html
    assert "主图可左右拖动" in html
    assert "installChartPan" in html
    assert "panActiveRange" in html
    assert "zoomActiveRange" in html
    assert 'viewBox="0 0 1000 165"' in html
    assert "https://invest.okbbc.com/header.js" in html
    assert "https://invest.okbbc.com/footer.js" in html


def test_index_compare_page_reuses_compare_shell_with_extra_metrics() -> None:
    html = render_index_compare_page()
    assert "指数总收益曲线对比" in html
    assert "/api/index-compare/history.json" in html
    assert 'data-extra-metrics="true"' in html
    assert 'data-synthetic-code="VIRTUAL_EQUAL_WEIGHT_INDEX"' in html
    assert "红利低波全收益" in html
    assert "最长回本时间" in html
    assert 'data-sort="longestRecoveryDays"' in html
    assert "滚动3年最差收益" in html
    assert 'data-sort="rollingThreeYearWorstReturn"' in html
    assert "rollingThreeYearWorstReturn" in html
    assert 'data-base-title="指数价值曲线"' in html
    assert 'data-y-axis="return"' in html
    assert 'id="pan-left"' in html
    assert 'id="zoom-in"' in html
    assert "installChartPan" in html
    assert "https://invest.okbbc.com/header.js" in html
    assert "https://invest.okbbc.com/footer.js" in html


def test_value_compare_page_renders_background_shell() -> None:
    html = render_strategy_index_compare_page()
    assert render_value_compare_page() == html
    assert "策略指数收益曲线对比" in html
    assert "/api/strategy-index-compare/history.json" in html
    assert 'data-extra-metrics="true"' in html
    assert 'data-synthetic-code="VIRTUAL_EQUAL_WEIGHT_STRATEGY"' in html
    assert 'data-risk-parity-code="VIRTUAL_RISK_PARITY_STRATEGY"' in html
    assert 'data-anchor-synthetic="false"' in html
    assert 'data-show-background="true"' in html
    assert "国信价值全收益" in html
    assert "创成长R" in html
    assert "价值100R" not in html
    assert "自由现金流R" in html
    assert "策略等权组合" in html
    assert "风险平价组合" in html
    assert "buildRiskParityRows" in html
    assert "inverseVolatilityWeights" in html
    assert "dynamicRiskParityRows" in html
    assert "上证指数作为灰色背景线" in html
    assert "background_series" in html
    assert "backgroundNormalizedSeries" in html
    assert "background-line" in html
    assert "最长回本时间" in html
    assert "滚动3年最差收益" in html
    assert "https://invest.okbbc.com/header.js" in html
    assert "https://invest.okbbc.com/footer.js" in html


def test_trend_channel_pages_render_interactive_shell() -> None:
    broad = render_trend_channel_page("broad")
    assert "宽基趋势图" in broad
    assert "/api/trend-channels/broad.json" in broad
    assert "fit-since2016" in broad
    assert "fit-all" in broad
    assert "trend-chart" in broad
    assert "drawdown-chart" in broad
    assert "轨道位置" in broad
    assert 'dom.summaryGrid.innerHTML = "<div class="empty">' not in broad
    assert 'dom.metricsBody.innerHTML = "<tr><td colspan="11">' not in broad
    assert "get_trend_channel_payload" not in broad
    assert "https://invest.okbbc.com/header.js" in broad
    assert "https://invest.okbbc.com/footer.js" in broad

    theme = render_trend_channel_page("theme")
    assert "主线指数趋势图" in theme
    assert "/api/trend-channels/theme.json" in theme
    assert "主线指数按代表性主题分组" in theme
    assert "统计轨道" in theme
    assert 'dom.summaryGrid.innerHTML = "<div class="empty">' not in theme
    assert 'dom.metricsBody.innerHTML = "<tr><td colspan="11">' not in theme


def test_capital_migration_page_renders_interactive_shell() -> None:
    html = render_capital_migration_page()
    assert "资金迁移雷达" in html
    assert "/api/capital-migration/radar.json" in html
    assert "价量承接代理" in html
    assert "流出压力" in html
    assert "承接强度" in html
    assert "迁移矩阵" in html
    assert "relative-chart" in html
    assert "data-window=\"5\"" in html
    assert "get_capital_migration_payload" not in html
    assert "https://invest.okbbc.com/header.js" in html
    assert "https://invest.okbbc.com/footer.js" in html


def test_qmt_snapshot_html_renders_ticks() -> None:
    html = _qmt_snapshot_html(
        {
            "updated_at": "2026-06-16T13:10:00",
            "ticks": {
                "000001.SZ": {
                    "lastPrice": 11.06,
                    "open": 11.0,
                    "high": 11.2,
                    "low": 10.9,
                    "time": "13:10:00",
                }
            },
        }
    )
    assert "000001.SZ" in html
    assert "11.060" in html


def test_intraday_table_html_renders_status() -> None:
    html = _intraday_table_html(
        [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "plan_action": "watch_if_trigger",
                "intraday_status": "triggered",
                "last_price": "11.4",
                "trigger_price": "11.39",
                "invalid_price": "10.63",
                "max_open_price": "11.45",
                "distance_to_trigger_pct": "0.001",
                "qmt_time": "20260616 13:00:00",
                "note": "last price reached trigger_price",
            }
        ]
    )
    assert "盘中监控" not in html
    assert "triggered" in html
    assert "11.400" in html


def test_alert_table_html_renders_recent_alert() -> None:
    html = _alert_table_html(
        [
            {
                "observed_at": "2026-06-16T13:00:00",
                "symbol": "000001.SZ",
                "name": "平安银行",
                "status": "triggered",
                "last_price": 11.4,
                "trigger_price": 11.39,
                "invalid_price": 10.63,
                "qmt_time": "20260616 13:00:00",
                "message": "000001.SZ reached trigger price",
            }
        ]
    )
    assert "000001.SZ" in html
    assert "triggered" in html
    assert "11.400" in html


def test_watch_status_html_renders_status() -> None:
    html = _watch_status_html(
        {
            "checked_at": "2026-06-16T13:00:00",
            "plan_file": "plan_20260616_090000.csv",
            "waiting": 2,
            "new_alerts": 1,
            "triggered": 1,
            "invalidated": 0,
            "gap_skip": 0,
            "no_tick": 0,
        }
    )
    assert "最近检查" in html
    assert "plan_20260616_090000.csv" in html
    assert "新提醒" in html


def test_action_controls_html_renders_run_buttons() -> None:
    html = _action_controls_html()
    assert "Run 监控" in html
    assert "一键盘中刷新" in html
    assert "/actions/intraday-refresh-all" in html
    assert "/actions/intraday-monitor" in html
    assert "Run 不写提醒" in html
    assert "导入持仓" in html
    assert "刷新全量行情" in html
    assert "/actions/qmt-realtime-coverage" in html


def test_run_intraday_action_writes_report_status_and_alert(tmp_path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "date": "2026-06-15",
                "action": "watch_if_trigger",
                "score": 65,
                "trigger_price": 11.39,
                "invalid_price": 10.63,
                "max_open_price": 11.45,
            }
        ]
    ).to_csv(reports_dir / "plan_20260616_090000.csv", index=False, encoding="utf-8-sig")
    (data_dir / "qmt_realtime.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-06-16T13:00:00",
                "ticks": {
                    "000001.SZ": {"lastPrice": 11.4, "open": 11.0, "timetag": "20260616 13:00:00"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")

    payload = run_intraday_action(settings, write_alerts=True)

    assert payload["ok"] is True
    assert payload["triggered"] == 1
    assert payload["new_alerts"] == 1
    assert (reports_dir / str(payload["csv"])).exists()
    assert (data_dir / "intraday_status.json").exists()
    assert len((data_dir / "intraday_alerts.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_position_snapshot_html_renders_positions(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    html = _position_snapshot_html(
        {
            "imported_at": "2026-06-16T14:00:00",
            "source_file": "positions.csv",
            "positions": [
                {
                    "symbol": "000001.SZ",
                    "name": "平安银行",
                    "quantity": 1000,
                    "available_quantity": 800,
                    "last_price": 10.5,
                    "market_value": 10500,
                    "cost_price": 9.8,
                    "profit_loss": 700,
                    "profit_loss_pct": 7.14,
                    "position_pct": 0.12,
                }
            ],
        },
        settings,
    )
    assert "000001.SZ" in html
    assert "平安银行" in html
    assert "7.14%" in html
    assert "12.00%" in html


def test_run_position_import_action_writes_snapshot(tmp_path, monkeypatch) -> None:
    source = tmp_path / "positions.csv"
    source.write_text("证券代码,证券名称,持仓数量,持仓市值\n000001,平安银行,1000,10500\n", encoding="utf-8-sig")
    env_file = tmp_path / ".env"
    env_file.write_text(f"QMT_POSITION_EXPORT={source}\n", encoding="utf-8")
    monkeypatch.delenv("QMT_POSITION_EXPORT", raising=False)
    monkeypatch.delenv("QMT_SDK_PATH", raising=False)
    monkeypatch.delenv("QMT_USERDATA_PATH", raising=False)
    monkeypatch.delenv("QMT_ACCOUNT_ID", raising=False)
    settings = load_settings(root=tmp_path, env_file=env_file)

    payload = run_position_import_action(settings)

    assert payload["ok"] is True
    assert payload["rows"] == 1
    assert (tmp_path / "data" / "qmt_positions_latest.json").exists()


def test_realtime_coverage_symbols_combines_positions_plan_and_config() -> None:
    symbols = _realtime_coverage_symbols(
        {
            "positions": [
                {"symbol": "510300.SH", "quantity": 100},
                {"symbol": "001399.SZ", "quantity": 100},
                {"symbol": "SPY", "quantity": 1},
            ]
        },
        [
            {"symbol": "000001.SZ", "action": "watch_if_trigger"},
            {"symbol": "600519.SH", "action": "blocked"},
            {"symbol": "SPY", "action": "watch_if_trigger"},
        ],
        ["000001.SZ", "BAD"],
    )

    assert symbols == ["000001.SZ", "001399.SZ", "510300.SH"]


def test_run_realtime_coverage_action_writes_snapshot(tmp_path, monkeypatch) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(
        [
            {"symbol": "000001.SZ", "name": "平安银行", "action": "watch_if_trigger"},
            {"symbol": "SPY", "name": "SPY", "action": "watch_if_trigger"},
        ]
    ).to_csv(reports_dir / "plan_20260616_090000.csv", index=False, encoding="utf-8-sig")
    (data_dir / "qmt_positions_latest.json").write_text(
        json.dumps(
            {
                "positions": [
                    {"symbol": "510300.SH", "name": "沪深300ETF", "quantity": 100},
                    {"symbol": "001399.SZ", "name": "国证2000ETF", "quantity": 100},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("QMT_REALTIME_SYMBOLS=000001.SZ\n", encoding="utf-8")
    monkeypatch.delenv("QMT_REALTIME_SYMBOLS", raising=False)
    monkeypatch.delenv("QMT_SDK_PATH", raising=False)
    settings = load_settings(root=tmp_path, env_file=env_file)
    captured: dict[str, object] = {}

    def fake_write_realtime_snapshot(path, provider, symbols):
        captured["symbols"] = symbols
        payload = {
            "updated_at": "2026-06-16T14:30:00",
            "symbols": symbols,
            "ticks": {symbol: {"lastPrice": 1.0} for symbol in symbols},
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    monkeypatch.setattr("shortterm_trader.webapp.write_realtime_snapshot", fake_write_realtime_snapshot)

    payload = run_realtime_coverage_action(settings)

    assert payload["ok"] is True
    assert payload["rows"] == 3
    assert payload["ticks"] == 3
    assert captured["symbols"] == ["000001.SZ", "001399.SZ", "510300.SH"]
    assert (data_dir / "qmt_realtime.json").exists()


def test_run_intraday_refresh_all_action_runs_ordered_steps(tmp_path, monkeypatch) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    calls: list[str] = []

    def fake_position_import(_settings):
        calls.append("positions")
        return {"ok": True, "rows": 2, "message": "positions"}

    def fake_realtime_coverage(_settings):
        calls.append("realtime")
        return {"ok": True, "rows": 3, "ticks": 3, "message": "realtime"}

    def fake_intraday(_settings, write_alerts=True):
        calls.append(f"intraday:{write_alerts}")
        return {"ok": True, "waiting": 1, "new_alerts": 1, "message": "intraday"}

    monkeypatch.setattr("shortterm_trader.webapp.run_position_import_action", fake_position_import)
    monkeypatch.setattr("shortterm_trader.webapp.run_realtime_coverage_action", fake_realtime_coverage)
    monkeypatch.setattr("shortterm_trader.webapp.run_intraday_action", fake_intraday)

    payload = run_intraday_refresh_all_action(settings)

    assert calls == ["positions", "realtime", "intraday:True"]
    assert payload["ok"] is True
    assert payload["position_rows"] == 2
    assert payload["realtime_ticks"] == 3
    assert payload["waiting"] == 1
    assert payload["new_alerts"] == 1
    assert "持仓 2 行" in str(payload["message"])


def test_today_work_rows_prioritizes_position_risk() -> None:
    rows = _today_work_rows(
        {
            "positions": [
                {
                    "symbol": "000001.SZ",
                    "name": "平安银行",
                    "quantity": 1000,
                    "position_pct": 0.12,
                },
                {
                    "symbol": "510500.SH",
                    "name": "中证500ETF南方",
                    "quantity": 100,
                    "position_pct": 0.02,
                },
            ]
        },
        [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "action": "watch_if_trigger",
                "score": "65",
                "trigger_price": "11.39",
                "invalid_price": "10.63",
            }
        ],
        [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "intraday_status": "invalidated",
                "last_price": "10.60",
                "trigger_price": "11.39",
                "invalid_price": "10.63",
                "distance_to_trigger_pct": "-0.069",
            }
        ],
        None,
    )

    assert rows[0]["symbol"] == "000001.SZ"
    assert rows[0]["level"] == "人工检查"
    assert rows[1]["symbol"] == "510500.SH"
    assert rows[1]["level"] == "补研究"


def test_today_work_research_group_sorts_by_priority() -> None:
    rows = _today_work_rows(
        {
            "positions": [
                {
                    "symbol": "510500.SH",
                    "name": "中证500ETF南方",
                    "quantity": 100,
                    "position_pct": 0.01,
                    "profit_loss_pct": 0.02,
                },
                {
                    "symbol": "512000.SH",
                    "name": "券商ETF",
                    "quantity": 100,
                    "position_pct": 0.12,
                    "profit_loss_pct": -0.08,
                },
                {
                    "symbol": "159001.SZ",
                    "name": "货币ETF",
                    "quantity": 100,
                    "position_pct": 0.02,
                    "profit_loss_pct": -0.02,
                },
            ]
        },
        [],
        [],
        {
            "ticks": {
                "510500.SH": {"lastPrice": 6.1},
                "512000.SH": {"lastPrice": 0.9},
            }
        },
    )

    research_rows = _today_work_group_rows(rows)["research"]

    assert [row["symbol"] for row in research_rows] == ["512000.SH", "159001.SZ", "510500.SH"]
    assert str(research_rows[0]["research_priority"]).startswith("高：")
    assert "仓位12.00%" in str(research_rows[0]["research_priority"])
    assert "浮亏8.00%" in str(research_rows[0]["research_priority"])
    assert "未进计划" in str(research_rows[0]["research_priority"])


def test_today_work_html_renders_actionable_table() -> None:
    html = _today_work_html(
        [
            {
                "level": "人工复核",
                "level_class": "work-focus",
                "symbol": "000001.SZ",
                "name": "平安银行",
                "kind": "观察",
                "status": "triggered",
                "last_price": 11.4,
                "position_pct": None,
                "trigger_price": 11.39,
                "invalid_price": 10.63,
                "distance_to_trigger_pct": 0.001,
                "reason": "观察票已达到触发价，人工复核后再决定",
            },
            {
                "level": "补研究",
                "level_class": "work-review",
                "symbol": "510500.SH",
                "name": "中证500ETF南方",
                "kind": "持仓",
                "status": "not_in_plan",
                "last_price": 6.1,
                "position_pct": 0.02,
                "profit_loss_pct": -0.03,
                "research_priority": "中：未进计划；无实时价",
                "trigger_price": None,
                "invalid_price": None,
                "distance_to_trigger_pct": None,
                "reason": "已持仓但不在最新计划里，先补研究和风控条件",
            },
            {
                "level": "持仓观察",
                "level_class": "work-muted",
                "symbol": "510300.SH",
                "name": "沪深300ETF",
                "kind": "持仓+计划",
                "status": "waiting",
                "last_price": 3.9,
                "position_pct": 0.05,
                "trigger_price": 4.0,
                "invalid_price": 3.7,
                "distance_to_trigger_pct": -0.025,
                "reason": "已持仓，当前未触发也未失效",
            }
        ]
    )

    assert "今日处理清单" not in html
    assert "必须检查" in html
    assert "优先级" in html
    assert "盈亏率" in html
    assert "<strong>1</strong> 必须检查" in html
    assert "<strong>1</strong> 补研究" in html
    assert "<strong>1</strong> 继续观察" in html
    assert "人工复核" in html
    assert "补研究" in html
    assert "继续观察" in html
    assert "中：未进计划；无实时价" in html
    assert "-3.00%" in html
    assert "已触发" in html
    assert "不在计划" in html
    assert "等待" in html
    assert "观察票已达到触发价" in html
