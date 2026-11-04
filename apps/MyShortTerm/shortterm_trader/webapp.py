from __future__ import annotations

import argparse
import csv
import html
import json
import re
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import pandas as pd

from shortterm_trader import __version__
from shortterm_trader.config import Settings, load_settings, redacted_source_status
from shortterm_trader.capital_migration import get_capital_migration_payload
from shortterm_trader.data.qmt import (
    QmtProvider,
    QmtUnavailable,
    import_position_export,
    import_terminal_positions,
    read_position_snapshot,
    read_realtime_snapshot,
    resolve_qmt_account_id,
    resolve_qmt_userdata_path,
    write_realtime_snapshot,
)
from shortterm_trader.data.store import SQLiteDataStore
from shortterm_trader.etf_compare import get_etf_compare_payload
from shortterm_trader.index_compare import get_index_compare_payload
from shortterm_trader.intraday import (
    MONITORED_ACTIONS,
    append_intraday_alerts,
    build_intraday_monitor,
    latest_plan_path,
    load_plan,
    read_intraday_alerts,
    read_intraday_status,
    write_intraday_reports,
    write_intraday_status,
)
from shortterm_trader.trend_channels import get_trend_channel_payload
from shortterm_trader.value_compare import get_value_compare_payload


A_SHARE_QMT_SYMBOL_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")
MYINVEST_HEADER_SCRIPT = "https://invest.okbbc.com/header.js"
MYINVEST_FOOTER_SCRIPT = "https://invest.okbbc.com/footer.js"


def _myinvest_header_html() -> str:
    return (
        '<div data-myinvest-header></div>\n'
        f'<script defer src="{MYINVEST_HEADER_SCRIPT}" data-target="[data-myinvest-header]"></script>'
    )


def _myinvest_footer_html() -> str:
    return (
        '<div data-myinvest-footer></div>\n'
        f'<script defer src="{MYINVEST_FOOTER_SCRIPT}" data-target="[data-myinvest-footer]"></script>'
    )


def _inject_unified_shell(page: str) -> str:
    return page.replace("__MYINVEST_HEADER__", _myinvest_header_html()).replace(
        "__MYINVEST_FOOTER__", _myinvest_footer_html()
    )


class DashboardHandler(BaseHTTPRequestHandler):
    settings: Settings

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_html(render_dashboard(self.settings))
            return
        if parsed.path == "/etf-compare":
            self._send_html(render_etf_compare_page())
            return
        if parsed.path == "/index-compare":
            self._send_html(render_index_compare_page())
            return
        if parsed.path in {"/value-compare", "/strategy-index-compare"}:
            self._send_html(render_strategy_index_compare_page())
            return
        if parsed.path == "/broad-trend":
            self._send_html(render_trend_channel_page("broad"))
            return
        if parsed.path == "/theme-trend":
            self._send_html(render_trend_channel_page("theme"))
            return
        if parsed.path == "/capital-migration":
            self._send_html(render_capital_migration_page())
            return
        if parsed.path == "/health.json":
            self._send_json({"ok": True, "version": __version__, "time": datetime.now().isoformat(timespec="seconds")})
            return
        if parsed.path == "/api/etf-compare/history.json":
            self._send_etf_compare_history(parsed.query)
            return
        if parsed.path == "/api/index-compare/history.json":
            self._send_index_compare_history(parsed.query)
            return
        if parsed.path in {"/api/value-compare/history.json", "/api/strategy-index-compare/history.json"}:
            self._send_value_compare_history(parsed.query)
            return
        if parsed.path == "/api/trend-channels/broad.json":
            self._send_trend_channel_history("broad", parsed.query)
            return
        if parsed.path == "/api/trend-channels/theme.json":
            self._send_trend_channel_history("theme", parsed.query)
            return
        if parsed.path == "/api/capital-migration/radar.json":
            self._send_capital_migration_radar(parsed.query)
            return
        if parsed.path.startswith("/reports/"):
            self._send_report(parsed.path.removeprefix("/reports/"))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        parsed = urlparse(self.path)
        if parsed.path == "/actions/intraday-monitor":
            self._send_action_result(write_alerts=True)
            return
        if parsed.path == "/actions/intraday-monitor-no-alerts":
            self._send_action_result(write_alerts=False)
            return
        if parsed.path == "/actions/qmt-positions":
            self._send_position_result()
            return
        if parsed.path == "/actions/qmt-realtime-coverage":
            self._send_realtime_coverage_result()
            return
        if parsed.path == "/actions/intraday-refresh-all":
            self._send_intraday_refresh_all_result()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_action_result(self, write_alerts: bool) -> None:
        if self.headers.get("X-MyShortTerm-Action") != "dashboard-action":
            self._send_json({"ok": False, "error": "Action header missing"}, status=HTTPStatus.FORBIDDEN)
            return
        try:
            payload = run_intraday_action(self.settings, write_alerts=write_alerts)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload)

    def _send_position_result(self) -> None:
        if self.headers.get("X-MyShortTerm-Action") != "dashboard-action":
            self._send_json({"ok": False, "error": "Action header missing"}, status=HTTPStatus.FORBIDDEN)
            return
        try:
            payload = run_position_import_action(self.settings)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload)

    def _send_realtime_coverage_result(self) -> None:
        if self.headers.get("X-MyShortTerm-Action") != "dashboard-action":
            self._send_json({"ok": False, "error": "Action header missing"}, status=HTTPStatus.FORBIDDEN)
            return
        try:
            payload = run_realtime_coverage_action(self.settings)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload)

    def _send_intraday_refresh_all_result(self) -> None:
        if self.headers.get("X-MyShortTerm-Action") != "dashboard-action":
            self._send_json({"ok": False, "error": "Action header missing"}, status=HTTPStatus.FORBIDDEN)
            return
        try:
            payload = run_intraday_refresh_all_action(self.settings)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload)

    def _send_etf_compare_history(self, raw_query: str) -> None:
        query = parse_qs(raw_query)
        refresh = (query.get("refresh", ["0"])[0] or "").lower() in {"1", "true", "yes", "y"}
        try:
            payload = get_etf_compare_payload(self.settings, refresh=refresh)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload)

    def _send_index_compare_history(self, raw_query: str) -> None:
        query = parse_qs(raw_query)
        refresh = (query.get("refresh", ["0"])[0] or "").lower() in {"1", "true", "yes", "y"}
        try:
            payload = get_index_compare_payload(self.settings, refresh=refresh)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload)

    def _send_value_compare_history(self, raw_query: str) -> None:
        query = parse_qs(raw_query)
        refresh = (query.get("refresh", ["0"])[0] or "").lower() in {"1", "true", "yes", "y"}
        try:
            payload = get_value_compare_payload(self.settings, refresh=refresh)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload)

    def _send_trend_channel_history(self, channel: str, raw_query: str) -> None:
        query = parse_qs(raw_query)
        refresh = (query.get("refresh", ["0"])[0] or "").lower() in {"1", "true", "yes", "y"}
        fit = query.get("fit", ["since2016"])[0] or "since2016"
        try:
            payload = get_trend_channel_payload(self.settings, channel, refresh=refresh, fit=fit)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload)

    def _send_capital_migration_radar(self, raw_query: str) -> None:
        query = parse_qs(raw_query)
        refresh = (query.get("refresh", ["0"])[0] or "").lower() in {"1", "true", "yes", "y"}
        try:
            window = int(query.get("window", ["5"])[0] or "5")
        except ValueError:
            window = 5
        try:
            payload = get_capital_migration_payload(self.settings, refresh=refresh, window=window)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload)

    def _send_report(self, raw_name: str) -> None:
        name = Path(unquote(raw_name)).name
        path = (self.settings.reports_dir / name).resolve()
        if not path.exists() or path.parent != self.settings.reports_dir.resolve():
            self.send_error(HTTPStatus.NOT_FOUND, "Report not found")
            return
        content_type = "text/markdown; charset=utf-8" if path.suffix.lower() == ".md" else "text/csv; charset=utf-8"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def render_dashboard(settings: Settings) -> str:
    status = redacted_source_status(settings)
    qmt_realtime = QmtProvider(settings.qmt_sdk_path).available()
    qmt_snapshot = read_realtime_snapshot(settings.qmt_realtime_path)
    position_snapshot = read_position_snapshot(settings.qmt_position_snapshot_path)
    reports = _latest_files(settings.reports_dir, ["*.md", "*.csv"], limit=8)
    caches = _latest_files(settings.cache_dir, ["*.csv"], limit=8)
    coverage = SQLiteDataStore(settings.db_path).coverage(limit=8)
    latest_plan = _latest_files(settings.reports_dir, ["plan_*.csv"], limit=1)
    plan_rows = _read_csv_preview(latest_plan[0]) if latest_plan else []
    intraday_rows = _intraday_rows(settings, qmt_snapshot)
    work_rows = _today_work_rows(position_snapshot, plan_rows, intraday_rows, qmt_snapshot)
    intraday_watch_status = read_intraday_status(settings.intraday_status_path)
    intraday_alerts = read_intraday_alerts(settings.intraday_alert_log_path, limit=8)
    latest_scan = _latest_files(settings.reports_dir, ["scan_*.csv"], limit=1)
    scan_rows = _read_csv_preview(latest_scan[0]) if latest_scan else []
    latest_backtest = _latest_files(settings.reports_dir, ["backtest_*.csv"], limit=1)
    metrics = _backtest_snapshot(latest_backtest[0]) if latest_backtest else {}

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>MyShortTerm</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1c2430;
      --muted: #687385;
      --line: #d9dee7;
      --accent: #0f766e;
      --accent-soft: #dff5f1;
      --warn: #a15c07;
      --bad: #b42318;
      --good: #157347;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      letter-spacing: 0;
    }}
    .page-header {{
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.96);
      backdrop-filter: blur(8px);
    }}
    .bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      max-width: 1280px;
      margin: 0 auto;
      padding: 14px 20px;
    }}
    h1 {{
      margin: 0;
      font-size: 20px;
      font-weight: 650;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
      color: var(--muted);
      font-size: 13px;
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      background: #fff;
      white-space: nowrap;
    }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 18px 20px 28px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.1fr 1.9fr;
      gap: 16px;
      align-items: start;
    }}
    section {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }}
    section h2 {{
      margin: 0;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 15px;
      font-weight: 650;
      background: #fbfcfd;
    }}
    .content {{ padding: 14px; }}
    .stack {{ display: grid; gap: 16px; }}
    .status-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .channel-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }}
    .channel-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      display: grid;
      gap: 6px;
      padding: 11px 12px;
      background: #fff;
      color: var(--text);
      text-decoration: none;
      min-height: 86px;
    }}
    .channel-card:hover {{
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-soft);
      text-decoration: none;
    }}
    .channel-title {{
      font-size: 15px;
      font-weight: 700;
    }}
    .channel-desc {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      min-height: 72px;
      background: #fff;
    }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 5px;
    }}
    .value {{
      font-size: 18px;
      font-weight: 650;
      overflow-wrap: anywhere;
    }}
    .ok {{ color: var(--good); }}
    .no {{ color: var(--bad); }}
    .warn {{ color: var(--warn); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 9px;
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      background: #fbfcfd;
    }}
    td:last-child, th:last-child {{ white-space: normal; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .empty {{
      color: var(--muted);
      padding: 12px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }}
    .signal-true {{
      color: var(--good);
      font-weight: 700;
    }}
    .signal-false {{ color: var(--muted); }}
    .action-candidate {{ color: var(--good); font-weight: 700; }}
    .action-watch {{ color: var(--warn); font-weight: 650; }}
    .action-blocked {{ color: var(--muted); }}
    .status-triggered {{ color: var(--good); font-weight: 700; }}
    .status-invalidated, .status-gap_skip {{ color: var(--bad); font-weight: 700; }}
    .status-waiting {{ color: var(--warn); font-weight: 650; }}
    .status-no_tick, .status-not_monitoring {{ color: var(--muted); }}
    .work-urgent {{ color: var(--bad); font-weight: 700; }}
    .work-focus {{ color: var(--warn); font-weight: 700; }}
    .work-review {{ color: var(--accent); font-weight: 700; }}
    .work-muted {{ color: var(--muted); }}
    .work-board {{
      display: grid;
      gap: 12px;
    }}
    .work-overview {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }}
    .work-overview strong {{ color: var(--text); }}
    .work-group {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .work-group summary {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      cursor: pointer;
      list-style: none;
      padding: 0 0 8px;
    }}
    .work-group summary::-webkit-details-marker {{ display: none; }}
    .work-group-title {{
      font-size: 14px;
      font-weight: 700;
    }}
    .work-group-meta {{
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    button {{
      border: 1px solid var(--accent);
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 650;
      padding: 7px 11px;
      cursor: pointer;
    }}
    button.secondary {{
      background: #fff;
      color: var(--accent);
    }}
    button:disabled {{
      cursor: wait;
      opacity: 0.65;
    }}
    .action-result {{
      color: var(--muted);
      font-size: 13px;
      min-height: 20px;
      margin-top: 10px;
    }}
    .note {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }}
    @media (max-width: 860px) {{
      .bar {{ align-items: flex-start; flex-direction: column; }}
      .meta {{ justify-content: flex-start; }}
      .grid {{ grid-template-columns: 1fr; }}
      .status-grid {{ grid-template-columns: 1fr; }}
      th, td {{ white-space: normal; }}
    }}
  </style>
</head>
<body>
  {_myinvest_header_html()}
  <div class="page-header">
    <div class="bar">
      <h1>MyShortTerm 短线研究面板</h1>
      <div class="meta">
        <span class="pill">v{html.escape(__version__)}</span>
        <a class="pill" href="/etf-compare">ETF 对比</a>
        <a class="pill" href="/index-compare">指数对比</a>
        <a class="pill" href="/strategy-index-compare">策略指数对比</a>
        <a class="pill" href="/broad-trend">宽基趋势图</a>
        <a class="pill" href="/theme-trend">主线指数趋势图</a>
        <a class="pill" href="/capital-migration">资金迁移雷达</a>
        <span class="pill">{html.escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</span>
        <span class="pill">60s 自动刷新</span>
      </div>
    </div>
  </div>
  <main>
    <section>
      <h2>研究频道</h2>
      <div class="content channel-grid">
        {_channel_card_html("/broad-trend", "宽基趋势图", "上证指数、中证全指、上证50、沪深300、中证500、创业板、自由现金流、红利低波。")}
        {_channel_card_html("/theme-trend", "主线指数趋势图", "新能源、电力设备、AI算力、通信、半导体、资源周期、军工、消费、创新药等主线。")}
        {_channel_card_html("/capital-migration", "资金迁移雷达", "观察宽基、科技、红利、周期、消费医药、防御现金之间的流出压力和承接强度。")}
        {_channel_card_html("/strategy-index-compare", "策略指数对比", "国信价值、创成长R、红利低波、自由现金流全收益；上证指数作背景。")}
        {_channel_card_html("/index-compare", "指数对比", "全收益指数和策略指数的收益、回撤、回本时间对比。")}
        {_channel_card_html("/etf-compare", "ETF 对比", "ETF复权价值曲线、回撤和动态等权组合对比。")}
      </div>
    </section>
    <div class="grid">
      <div class="stack">
        <section>
          <h2>数据源状态</h2>
          <div class="content status-grid">
            {_status_card("Tushare", bool(status["tushare_token"]))}
            {_status_card("FRED", bool(status["fred_api_key"]))}
            {_status_card("QMT 实时行情", qmt_realtime or bool(qmt_snapshot), _qmt_status_detail(qmt_realtime, qmt_snapshot))}
            {_status_card("QMT 真实持仓", bool(settings.qmt_sdk_path or settings.qmt_userdata_path or settings.qmt_position_export), _qmt_position_detail(settings))}
            {_status_card(".env", bool(status["env_file_exists"]), "本机读取")}
            {_status_card("本地库", settings.db_path.exists(), settings.db_path.name)}
          </div>
        </section>
        <section>
          <h2>回测快照</h2>
          <div class="content">
            {_metrics_html(metrics)}
          </div>
        </section>
        <section>
          <h2>最近文件</h2>
          <div class="content">
            {_file_list_html(reports, "reports")}
          </div>
        </section>
        <section>
          <h2>QMT 实时快照</h2>
          <div class="content">
            {_qmt_snapshot_html(qmt_snapshot)}
          </div>
        </section>
        <section>
          <h2>真实持仓</h2>
          <div class="content">
            {_position_snapshot_html(position_snapshot, settings)}
          </div>
        </section>
      </div>
      <div class="stack">
        <section>
          <h2>手动运行</h2>
          <div class="content">
            {_action_controls_html()}
          </div>
        </section>
        <section>
          <h2>今日处理清单</h2>
          <div class="content">
            {_today_work_html(work_rows)}
          </div>
        </section>
        <section>
          <h2>自动监控</h2>
          <div class="content">
            {_watch_status_html(intraday_watch_status)}
          </div>
        </section>
        <section>
          <h2>盘中提醒</h2>
          <div class="content">
            {_alert_table_html(intraday_alerts)}
          </div>
        </section>
        <section>
          <h2>盘中监控</h2>
          <div class="content">
            {_intraday_table_html(intraday_rows)}
          </div>
        </section>
        <section>
          <h2>明日计划</h2>
          <div class="content">
            {_plan_table_html(plan_rows)}
          </div>
        </section>
        <section>
          <h2>最新扫描</h2>
          <div class="content">
            {_scan_table_html(scan_rows)}
          </div>
        </section>
        <section>
          <h2>本地行情库</h2>
          <div class="content">
            {_coverage_table_html(coverage.to_dict("records"))}
          </div>
        </section>
        <section>
          <h2>缓存行情</h2>
          <div class="content">
            {_file_list_html(caches, "cache")}
          </div>
        </section>
        <section>
          <h2>边界</h2>
          <div class="content note">
            QMT 实时行情用于盘中价格；QMT 真实持仓优先从独立交易端只读查询，终端不可用时可读取持仓导出文件。当前系统只展示研究和监控结果；不连接交易写入，不自动下单，不展示真实密钥或完整账号。
          </div>
        </section>
      </div>
    </div>
</main>
{_myinvest_footer_html()}
<script>
  const actionOutput = document.getElementById("action-output");
  const actionButtons = Array.from(document.querySelectorAll("[data-action-path]"));
  async function runDashboardAction(button) {{
    const path = button.getAttribute("data-action-path");
    actionButtons.forEach((item) => item.disabled = true);
    actionOutput.textContent = "运行中...";
    try {{
      const response = await fetch(path, {{
        method: "POST",
        headers: {{"X-MyShortTerm-Action": "dashboard-action"}}
      }});
      const payload = await response.json();
      if (!response.ok || !payload.ok) {{
        throw new Error(payload.error || "运行失败");
      }}
      actionOutput.textContent = payload.message || `完成：观察中 ${{payload.waiting}}，新提醒 ${{payload.new_alerts}}`;
      window.setTimeout(() => window.location.reload(), 700);
    }} catch (error) {{
      actionOutput.textContent = `失败：${{error.message}}`;
      actionButtons.forEach((item) => item.disabled = false);
    }}
  }}
  actionButtons.forEach((button) => {{
    button.addEventListener("click", () => runDashboardAction(button));
  }});
</script>
</body>
</html>"""


def render_etf_compare_page() -> str:
    page = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ETF 复权对比 - MyShortTerm</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1c2430;
      --muted: #687385;
      --line: #d9dee7;
      --accent: #0f766e;
      --soft: #edf7f5;
      --bad: #b42318;
      --good: #157347;
      --warn: #a15c07;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      letter-spacing: 0;
    }
    .page-header {
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.97);
    }
    .bar {
      max-width: 1440px;
      margin: 0 auto;
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 700;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .meta {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      background: #fff;
      white-space: nowrap;
    }
    main {
      max-width: 1600px;
      margin: 0 auto;
      padding: 18px 20px 28px;
      display: grid;
      gap: 16px;
      align-items: start;
    }
    .control-panel, section {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }
    .panel-title {
      margin: 0;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 15px;
      font-weight: 700;
      background: #fbfcfd;
    }
    .content { padding: 14px; }
    .stack { display: grid; gap: 16px; }
    .controls-layout {
      display: grid;
      grid-template-columns: minmax(420px, 1.4fr) minmax(320px, 0.95fr) minmax(210px, 0.65fr) minmax(240px, 0.75fr);
      gap: 16px;
      align-items: start;
    }
    .control-group { display: grid; gap: 10px; }
    .control-title {
      font-size: 13px;
      font-weight: 700;
      color: var(--muted);
    }
    .instrument-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 8px 14px;
    }
    .instrument {
      display: grid;
      grid-template-columns: auto 14px 1fr;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      line-height: 1.35;
    }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 2px;
      display: inline-block;
    }
    .date-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .control-note {
      grid-column: 1 / -1;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }
    label span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }
    input[type="date"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 8px;
      font: inherit;
      background: #fff;
    }
    .quick-buttons, .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    button {
      border: 1px solid var(--accent);
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 650;
      padding: 7px 10px;
      cursor: pointer;
      min-height: 34px;
    }
    button.secondary {
      background: #fff;
      color: var(--accent);
    }
    button:disabled {
      cursor: wait;
      opacity: 0.65;
    }
    .icon-button {
      width: 34px;
      padding: 7px 0;
      text-align: center;
    }
    .note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.55;
    }
    .status {
      min-height: 20px;
      color: var(--muted);
      font-size: 13px;
    }
    .status.error { color: var(--bad); }
    .status.ok { color: var(--good); }
    .chart-wrap {
      padding: 12px 14px 14px;
    }
    .chart-head {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      margin-bottom: 8px;
      flex-wrap: wrap;
    }
    .chart-title {
      font-size: 15px;
      font-weight: 700;
    }
    .chart-meta {
      color: var(--muted);
      font-size: 12px;
    }
    svg {
      width: 100%;
      height: auto;
      display: block;
      overflow: visible;
    }
    .main-chart svg { min-height: 370px; }
    .drawdown-chart svg { min-height: 165px; }
    .metric-bars svg {
      height: 120px;
      min-height: 0;
    }
    .axis text {
      fill: var(--muted);
      font-size: 12px;
    }
    .axis line, .grid-line {
      stroke: #e8ebf0;
      stroke-width: 1;
    }
    .zero-line {
      stroke: #9aa3af;
      stroke-width: 1;
    }
    .series-line {
      fill: none;
      stroke-width: 2.4;
      stroke-linejoin: round;
      stroke-linecap: round;
    }
    .background-line {
      fill: none;
      stroke: #94a3b8;
      stroke-width: 1.8;
      stroke-linejoin: round;
      stroke-linecap: round;
      stroke-dasharray: 6 5;
      opacity: 0.68;
    }
    .background-label {
      fill: #64748b;
      font-size: 12px;
    }
    #value-chart {
      cursor: grab;
      touch-action: none;
    }
    #value-chart.dragging {
      cursor: grabbing;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px 9px;
      text-align: right;
      white-space: nowrap;
    }
    th:first-child, td:first-child {
      text-align: left;
      white-space: normal;
    }
    th {
      color: var(--muted);
      font-weight: 650;
      background: #fbfcfd;
    }
    th[data-sort] {
      cursor: pointer;
      user-select: none;
    }
    th[data-sort]::after {
      content: " ↕";
      color: #9aa3af;
      font-weight: 500;
    }
    th.sorted-asc::after { content: " ↑"; color: var(--accent); }
    th.sorted-desc::after { content: " ↓"; color: var(--accent); }
    .positive { color: var(--good); font-weight: 650; }
    .negative { color: var(--bad); font-weight: 650; }
    .empty {
      color: var(--muted);
      padding: 12px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }
    @media (max-width: 980px) {
      .bar { align-items: flex-start; flex-direction: column; }
      .meta { justify-content: flex-start; }
      .controls-layout { grid-template-columns: 1fr; }
      .date-row { grid-template-columns: 1fr; }
      th, td { white-space: normal; }
    }
  </style>
</head>
<body>
  __MYINVEST_HEADER__
  <div class="page-header">
    <div class="bar">
      <h1>ETF 复权价值曲线对比</h1>
      <div class="meta">
        <a class="pill" href="/">返回面板</a>
        <span class="pill">主图可左右拖动</span>
        <span class="pill">日线复权口径</span>
      </div>
    </div>
  </div>
  <main>
    <section class="control-panel">
      <h2 class="panel-title">对比设置</h2>
      <div class="content controls-layout">
        <div class="control-group">
          <div class="control-title">标的</div>
          <div id="instrument-list" class="instrument-list"></div>
        </div>
        <div class="control-group">
          <div class="control-title">时间范围</div>
          <div class="quick-buttons">
            <button id="mode-longest" type="button" data-mode="longest">2012起</button>
            <button id="mode-common" type="button" class="secondary" data-mode="common">共同区间</button>
          </div>
          <div class="quick-buttons">
            <button type="button" class="secondary" data-range="all">全部</button>
            <button type="button" class="secondary" data-years="1">近1年</button>
            <button type="button" class="secondary" data-years="3">近3年</button>
            <button type="button" class="secondary" data-years="5">近5年</button>
            <button type="button" class="secondary" data-years="6">近6年</button>
            <button type="button" class="secondary" data-years="7">近7年</button>
            <button type="button" class="secondary" data-years="8">近8年</button>
            <button type="button" class="secondary" data-years="9">近9年</button>
            <button type="button" class="secondary" data-years="10">近10年</button>
            <button type="button" class="secondary" data-since="2021-01-01">2021以来</button>
          </div>
          <div class="date-row">
            <label><span>开始</span><input id="start-date" type="date"></label>
            <label><span>结束</span><input id="end-date" type="date"></label>
          </div>
        </div>
        <div class="control-group">
          <div class="control-title">Y轴</div>
          <div class="quick-buttons">
            <button id="axis-return" type="button" data-y-axis="return">累计收益率%</button>
            <button id="axis-multiple" type="button" class="secondary" data-y-axis="multiple">净值倍数</button>
            <button id="axis-log" type="button" class="secondary" data-y-axis="log">对数</button>
          </div>
        </div>
        <div class="control-group">
          <div class="control-title">操作</div>
          <div class="actions">
            <button id="pan-left" type="button" class="secondary icon-button" title="左移" aria-label="左移">←</button>
            <button id="zoom-in" type="button" class="secondary icon-button" title="放大" aria-label="放大">+</button>
            <button id="zoom-out" type="button" class="secondary icon-button" title="缩小" aria-label="缩小">-</button>
            <button id="pan-right" type="button" class="secondary icon-button" title="右移" aria-label="右移">→</button>
            <button id="reset-range" type="button" class="secondary">恢复全区间</button>
            <button id="refresh-data" type="button">更新数据</button>
          </div>
          <div id="status" class="status">准备加载数据...</div>
        </div>
        <div class="note control-note">
          2012起模式按最早可用 ETF 开始展示；后上市 ETF 从上市日对应的虚拟等权ETF位置接上。虚拟等权ETF按 512890、510500、510300、159915 四只真实 ETF 中当日已有数据的成分动态等权；480092 为自由现金流R收益指数点位代理。
        </div>
      </div>
    </section>
    <div class="stack">
      <section class="main-chart">
        <div class="chart-wrap">
          <div class="chart-head">
            <div id="value-chart-title" class="chart-title" data-base-title="复权价值曲线">复权价值曲线</div>
            <div id="range-hint" class="chart-meta">-</div>
          </div>
          <svg id="value-chart" viewBox="0 0 1000 390" role="img" aria-label="复权价值曲线"></svg>
        </div>
      </section>
      <section class="drawdown-chart">
        <div class="chart-wrap">
          <div class="chart-head">
            <div class="chart-title">回撤曲线</div>
            <div class="chart-meta">越接近 0 越好</div>
          </div>
          <svg id="drawdown-chart" viewBox="0 0 1000 165" role="img" aria-label="回撤曲线"></svg>
        </div>
      </section>
      <section class="metric-bars">
        <div class="chart-wrap">
          <div class="chart-head">
            <div class="chart-title">年化收益 vs 最大回撤</div>
            <div class="chart-meta">当前区间动态计算</div>
          </div>
          <svg id="bar-chart" viewBox="0 0 1000 120" role="img" aria-label="年化收益与最大回撤柱状图"></svg>
        </div>
      </section>
      <section>
        <h2 class="panel-title">指标对比</h2>
        <div class="content">
          <table>
            <thead>
              <tr>
                <th data-sort="name">标的</th>
                <th data-sort="totalReturn">总收益</th>
                <th data-sort="maxReturn">区间最高收益</th>
                <th data-sort="annualizedReturn" class="sorted-desc">年化收益</th>
                <th data-sort="maxDrawdown">最大回撤</th>
                <th data-sort="annualizedVolatility">年化波动</th>
                <th data-sort="annualizedReturnDrawdownRatio">年化收益/最大回撤</th>
              </tr>
            </thead>
            <tbody id="metrics-body"></tbody>
          </table>
        </div>
      </section>
      <section id="errors-section" hidden>
        <h2 class="panel-title">数据提示</h2>
        <div id="errors" class="content note"></div>
      </section>
    </div>
  </main>
  __MYINVEST_FOOTER__
<script>
const MS_DAY = 24 * 60 * 60 * 1000;
const VALUE_BOX = { width: 1000, height: 390, plot: { left: 58, right: 20, top: 22, bottom: 38 } };
const DRAW_BOX = { width: 1000, height: 165, plot: { left: 58, right: 20, top: 14, bottom: 30 } };
const BAR_BOX = { width: 1000, height: 120, plot: { left: 46, right: 18, top: 18, bottom: 30 } };
const API_PATH = document.body.dataset.apiPath || "/api/etf-compare/history.json";
const SYNTHETIC_CODE = document.body.dataset.syntheticCode || "VIRTUAL_EQUAL_WEIGHT";
const RISK_PARITY_CODE = document.body.dataset.riskParityCode || "";
const ANCHOR_TO_SYNTHETIC = document.body.dataset.anchorSynthetic !== "false";
const LONGEST_MODE_LABEL = document.body.dataset.longestModeLabel || "2012起";
const LONGEST_BASE_TEXT = document.body.dataset.longestBaseText || "后上市标的接到虚拟等权ETF位置";
const INCLUDE_RECOVERY_METRICS = document.body.dataset.extraMetrics === "true";
const SHOW_BACKGROUND = document.body.dataset.showBackground === "true";
const VALUE_AXIS_MODES = {
  return: { title: "累计收益率%", baseline: 0 },
  multiple: { title: "净值倍数", baseline: 1 },
  log: { title: "对数累计收益率%", baseline: 1 },
};

const state = {
  payload: null,
  selected: new Set(),
  drag: null,
  dynamicSyntheticRows: [],
  dynamicRiskParityRows: [],
  rangeMode: "longest",
  valueAxisMode: "return",
  sortKey: "annualizedReturn",
  sortDirection: "desc",
};

const dom = {
  instruments: document.getElementById("instrument-list"),
  start: document.getElementById("start-date"),
  end: document.getElementById("end-date"),
  status: document.getElementById("status"),
  hint: document.getElementById("range-hint"),
  valueTitle: document.getElementById("value-chart-title"),
  valueChart: document.getElementById("value-chart"),
  drawdownChart: document.getElementById("drawdown-chart"),
  barChart: document.getElementById("bar-chart"),
  metricsBody: document.getElementById("metrics-body"),
  errorsSection: document.getElementById("errors-section"),
  errors: document.getElementById("errors"),
  refresh: document.getElementById("refresh-data"),
  reset: document.getElementById("reset-range"),
  panLeft: document.getElementById("pan-left"),
  panRight: document.getElementById("pan-right"),
  zoomIn: document.getElementById("zoom-in"),
  zoomOut: document.getElementById("zoom-out"),
  axisReturn: document.getElementById("axis-return"),
  axisMultiple: document.getElementById("axis-multiple"),
  axisLog: document.getElementById("axis-log"),
  modeCommon: document.getElementById("mode-common"),
  modeLongest: document.getElementById("mode-longest"),
};
const VALUE_TITLE_BASE = dom.valueTitle?.dataset.baseTitle || "价值曲线";

function setStatus(text, kind = "") {
  dom.status.textContent = text;
  dom.status.className = `status ${kind}`.trim();
}

function parseDate(value) {
  return new Date(`${value}T00:00:00+08:00`).getTime();
}

function fmtDate(ms) {
  const d = new Date(ms);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function pct(value) {
  if (!Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(2)}%`;
}

function ratioText(value) {
  if (!Number.isFinite(value)) return "-";
  return value.toFixed(2);
}

function valueAxisConfig() {
  return VALUE_AXIS_MODES[state.valueAxisMode] || VALUE_AXIS_MODES.return;
}

function valueAxisLabel() {
  return valueAxisConfig().title;
}

function commonBaseText() {
  if (state.valueAxisMode === "multiple") return "共同起点=1x";
  if (state.valueAxisMode === "log") return "共同起点=0%（对数）";
  return "共同起点=0%";
}

function valueAxisY(rawValue) {
  const multiple = rawValue / 100;
  if (state.valueAxisMode === "multiple" || state.valueAxisMode === "log") return multiple;
  return multiple - 1;
}

function formatValueAxis(value) {
  if (state.valueAxisMode === "multiple") {
    if (Math.abs(value) >= 10) return `${value.toFixed(0)}x`;
    return `${value.toFixed(1)}x`;
  }
  const pctValue = state.valueAxisMode === "log" ? (value - 1) * 100 : value * 100;
  if (Math.abs(pctValue) >= 100) return `${pctValue.toFixed(0)}%`;
  return `${pctValue.toFixed(1)}%`;
}

function recoveryText(days) {
  if (!Number.isFinite(days)) return "-";
  if (days < 30) return `${Math.round(days)}天`;
  return `${(days / 365.25).toFixed(1)}年`;
}

function metricColumnCount() {
  return INCLUDE_RECOVERY_METRICS ? 9 : 7;
}

function moneyText(value) {
  if (!Number.isFinite(value)) return "-";
  return value.toFixed(1);
}

function svgEl(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, String(value));
  }
  return node;
}

function clearSvg(svg) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
}

async function loadHistory(refresh = false) {
  dom.refresh.disabled = true;
  setStatus(refresh ? "正在更新历史数据..." : "正在加载历史数据...");
  try {
    const response = await fetch(`${API_PATH}${refresh ? "?refresh=1" : ""}`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "历史数据加载失败");
    }
    for (const rows of Object.values(payload.series)) {
      rows.forEach((row) => {
        row.dateMs = parseDate(row.date);
        row.close = Number(row.close);
        row.value = Number(row.value);
      });
    }
    if (Array.isArray(payload.background_series)) {
      payload.background_series.forEach((row) => {
        row.dateMs = parseDate(row.date);
        row.close = Number(row.close);
        row.value = Number(row.value);
      });
    }
    state.payload = payload;
    state.selected = new Set(payload.instruments.filter((item) => payload.series[item.code]?.length).map((item) => item.code));
    renderInstrumentControls();
    setRangeToCurrentMode();
    renderAll();
    setStatus(refresh ? "数据已更新" : "数据已加载", "ok");
  } catch (error) {
    setStatus(`失败：${error.message}`, "error");
  } finally {
    dom.refresh.disabled = false;
  }
}

function renderInstrumentControls() {
  dom.instruments.innerHTML = "";
  state.payload.instruments.forEach((item) => {
    const hasData = Boolean(state.payload.series[item.code]?.length);
    const label = document.createElement("label");
    label.className = "instrument";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = item.code;
    input.checked = state.selected.has(item.code);
    input.disabled = !hasData;
    input.addEventListener("change", () => {
      if (input.checked) state.selected.add(item.code);
      else state.selected.delete(item.code);
      clampInputsToCurrentMode();
      renderAll();
    });
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = item.color;
    const text = document.createElement("span");
    text.textContent = hasData ? item.name : `${item.name}（无数据）`;
    label.append(input, swatch, text);
    dom.instruments.appendChild(label);
  });
}

function selectedCodes() {
  return Array.from(state.selected).filter((code) => state.payload.series[code]?.length);
}

function isSyntheticCode(code) {
  return code === SYNTHETIC_CODE || (RISK_PARITY_CODE && code === RISK_PARITY_CODE);
}

function selectedComponentCodes() {
  return selectedCodes().filter((code) => !isSyntheticCode(code));
}

function boundsCodes(codes = selectedCodes()) {
  const output = [];
  codes.forEach((code) => {
    if (isSyntheticCode(code)) output.push(...selectedComponentCodes());
    else output.push(code);
  });
  return Array.from(new Set(output)).filter((code) => state.payload.series[code]?.length);
}

function getCommonBounds(codes = selectedCodes()) {
  codes = boundsCodes(codes);
  if (!codes.length) return null;
  const starts = [];
  const ends = [];
  codes.forEach((code) => {
    const rows = state.payload.series[code] || [];
    if (rows.length) {
      starts.push(rows[0].dateMs);
      ends.push(rows[rows.length - 1].dateMs);
    }
  });
  if (!starts.length) return null;
  return { start: Math.max(...starts), end: Math.min(...ends) };
}

function getLongestBounds(codes = selectedCodes()) {
  codes = boundsCodes(codes);
  if (!codes.length) return null;
  const starts = [];
  const ends = [];
  codes.forEach((code) => {
    const rows = state.payload.series[code] || [];
    if (rows.length) {
      starts.push(rows[0].dateMs);
      ends.push(rows[rows.length - 1].dateMs);
    }
  });
  if (!starts.length) return null;
  return { start: Math.min(...starts), end: Math.max(...ends) };
}

function currentBounds() {
  return state.rangeMode === "longest" ? getLongestBounds() : getCommonBounds();
}

function setRangeToCurrentMode() {
  const bounds = currentBounds();
  if (!bounds) return;
  dom.start.value = fmtDate(bounds.start);
  dom.end.value = fmtDate(bounds.end);
}

function clampInputsToCurrentMode() {
  const bounds = currentBounds();
  if (!bounds) return;
  let start = dom.start.value ? parseDate(dom.start.value) : bounds.start;
  let end = dom.end.value ? parseDate(dom.end.value) : bounds.end;
  start = Math.max(start, bounds.start);
  end = Math.min(end, bounds.end);
  if (start > end) {
    start = bounds.start;
    end = bounds.end;
  }
  dom.start.value = fmtDate(start);
  dom.end.value = fmtDate(end);
}

function activeRange() {
  const bounds = currentBounds();
  if (!bounds) return null;
  let start = dom.start.value ? parseDate(dom.start.value) : bounds.start;
  let end = dom.end.value ? parseDate(dom.end.value) : bounds.end;
  start = Math.max(start, bounds.start);
  end = Math.min(end, bounds.end);
  if (start > end) {
    const tmp = start;
    start = end;
    end = tmp;
  }
  return { start, end, commonStart: bounds.start, commonEnd: bounds.end };
}

function setActiveRange(start, end, shouldRender = true) {
  const bounds = currentBounds();
  if (!bounds) return false;
  let nextStart = Number(start);
  let nextEnd = Number(end);
  if (!Number.isFinite(nextStart) || !Number.isFinite(nextEnd)) return false;
  if (nextStart > nextEnd) {
    const tmp = nextStart;
    nextStart = nextEnd;
    nextEnd = tmp;
  }
  const boundsSpan = Math.max(bounds.end - bounds.start, MS_DAY);
  let span = Math.max(nextEnd - nextStart, MS_DAY);
  if (span >= boundsSpan) {
    nextStart = bounds.start;
    nextEnd = bounds.end;
  } else {
    if (nextStart < bounds.start) {
      nextEnd += bounds.start - nextStart;
      nextStart = bounds.start;
    }
    if (nextEnd > bounds.end) {
      nextStart -= nextEnd - bounds.end;
      nextEnd = bounds.end;
    }
    nextStart = Math.max(bounds.start, nextStart);
    nextEnd = Math.min(bounds.end, nextEnd);
  }
  dom.start.value = fmtDate(nextStart);
  dom.end.value = fmtDate(nextEnd);
  if (shouldRender) renderAll();
  return true;
}

function rowsInRange(code, range) {
  if (code === SYNTHETIC_CODE) {
    return state.dynamicSyntheticRows.filter((row) => row.dateMs >= range.start && row.dateMs <= range.end);
  }
  if (RISK_PARITY_CODE && code === RISK_PARITY_CODE) {
    return state.dynamicRiskParityRows.filter((row) => row.dateMs >= range.start && row.dateMs <= range.end);
  }
  return (state.payload.series[code] || []).filter((row) => row.dateMs >= range.start && row.dateMs <= range.end);
}

function calculateMetrics(rows) {
  if (rows.length < 2) return null;
  const first = rows[0];
  const last = rows[rows.length - 1];
  const base = first.value;
  const totalReturn = last.value / base - 1;
  const days = Math.max((last.dateMs - first.dateMs) / MS_DAY, 1);
  const annualizedReturn = Math.pow(last.value / base, 365.25 / days) - 1;
  let peak = -Infinity;
  let peakDateMs = first.dateMs;
  let underwaterStartMs = null;
  let maxDrawdown = 0;
  let maxReturn = -Infinity;
  let longestRecoveryDays = 0;
  const dailyReturns = [];
  rows.forEach((row, index) => {
    if (row.value >= peak) {
      if (underwaterStartMs !== null) {
        longestRecoveryDays = Math.max(longestRecoveryDays, (row.dateMs - underwaterStartMs) / MS_DAY);
        underwaterStartMs = null;
      }
      peak = row.value;
      peakDateMs = row.dateMs;
    } else if (underwaterStartMs === null) {
      underwaterStartMs = peakDateMs;
    }
    maxDrawdown = Math.min(maxDrawdown, row.value / peak - 1);
    maxReturn = Math.max(maxReturn, row.value / base - 1);
    if (index > 0) {
      const prev = rows[index - 1].value;
      if (prev > 0) dailyReturns.push(row.value / prev - 1);
    }
  });
  if (underwaterStartMs !== null) {
    longestRecoveryDays = Math.max(longestRecoveryDays, (last.dateMs - underwaterStartMs) / MS_DAY);
  }
  const rollingWindowMs = 3 * 365.25 * MS_DAY;
  let rollingThreeYearWorstReturn = NaN;
  let endIndex = 0;
  rows.forEach((startRow) => {
    const targetDate = startRow.dateMs + rollingWindowMs;
    while (endIndex < rows.length && rows[endIndex].dateMs < targetDate) endIndex += 1;
    if (endIndex < rows.length && startRow.value > 0) {
      const rollingReturn = rows[endIndex].value / startRow.value - 1;
      rollingThreeYearWorstReturn = Number.isFinite(rollingThreeYearWorstReturn)
        ? Math.min(rollingThreeYearWorstReturn, rollingReturn)
        : rollingReturn;
    }
  });
  const avg = dailyReturns.reduce((sum, item) => sum + item, 0) / Math.max(dailyReturns.length, 1);
  const variance = dailyReturns.reduce((sum, item) => sum + Math.pow(item - avg, 2), 0) / Math.max(dailyReturns.length - 1, 1);
  const annualizedVolatility = Math.sqrt(variance) * Math.sqrt(252);
  return {
    totalReturn,
    maxReturn,
    annualizedReturn,
    maxDrawdown,
    annualizedVolatility,
    annualizedReturnDrawdownRatio: annualizedReturn / Math.abs(maxDrawdown || NaN),
    longestRecoveryDays,
    rollingThreeYearWorstReturn,
  };
}

function equalWeightAnchor(dateMs, range) {
  const equalRows = rowsInRange(SYNTHETIC_CODE, range);
  if (!equalRows.length) return 100;
  const base = equalRows[0].value;
  let anchorRow = equalRows[0];
  for (const row of equalRows) {
    if (row.dateMs <= dateMs) anchorRow = row;
    else break;
  }
  return anchorRow.value / base * 100;
}

function buildDynamicSyntheticRows(range) {
  const componentRows = selectedComponentCodes()
    .map((code) => rowsInRange(code, range))
    .filter((rows) => rows.length >= 2);
  if (!componentRows.length) return [];

  const allDates = new Set();
  const returnMaps = componentRows.map((rows) => {
    const returns = new Map();
    rows.forEach((row) => allDates.add(row.dateMs));
    rows.forEach((row, index) => {
      if (index === 0) return;
      const prev = rows[index - 1].value;
      if (prev > 0) returns.set(row.dateMs, row.value / prev - 1);
    });
    return returns;
  });
  const dates = Array.from(allDates).sort((left, right) => left - right);
  let value = 1;
  return dates.map((dateMs, index) => {
    if (index > 0) {
      const availableReturns = returnMaps
        .filter((returns) => returns.has(dateMs))
        .map((returns) => returns.get(dateMs))
        .filter(Number.isFinite);
      if (availableReturns.length) {
        value *= 1 + availableReturns.reduce((sum, item) => sum + item, 0) / availableReturns.length;
      }
    }
    return { dateMs, close: value, value };
  });
}

function buildRiskParityRows(range) {
  if (!RISK_PARITY_CODE) return [];
  const componentRows = selectedComponentCodes()
    .map((code) => rowsInRange(code, range))
    .filter((rows) => rows.length >= 2);
  if (componentRows.length < 2) return [];

  const allDates = new Set();
  const returnMaps = componentRows.map((rows) => {
    const returns = new Map();
    rows.forEach((row) => allDates.add(row.dateMs));
    rows.forEach((row, index) => {
      if (index === 0) return;
      const prev = rows[index - 1].value;
      if (prev > 0) returns.set(row.dateMs, row.value / prev - 1);
    });
    return returns;
  });
  const dates = Array.from(allDates).sort((left, right) => left - right);
  const trailingReturns = returnMaps.map(() => []);
  let value = 1;
  return dates.map((dateMs, index) => {
    const available = returnMaps
      .map((returns, assetIndex) => ({
        assetIndex,
        dailyReturn: returns.get(dateMs),
        volatility: trailingVolatility(trailingReturns[assetIndex]),
      }))
      .filter((item) => Number.isFinite(item.dailyReturn));
    if (index > 0 && available.length) {
      const weights = inverseVolatilityWeights(available.map((item) => item.volatility));
      const portfolioReturn = available.reduce((sum, item, itemIndex) => sum + item.dailyReturn * weights[itemIndex], 0);
      value *= 1 + portfolioReturn;
    }
    returnMaps.forEach((returns, assetIndex) => {
      const dailyReturn = returns.get(dateMs);
      if (Number.isFinite(dailyReturn)) trailingReturns[assetIndex].push(dailyReturn);
    });
    return { dateMs, close: value, value };
  });
}

function trailingVolatility(values, window = 60) {
  const recent = values.slice(-window).filter(Number.isFinite);
  if (recent.length < 20) return NaN;
  const avg = recent.reduce((sum, item) => sum + item, 0) / recent.length;
  const variance = recent.reduce((sum, item) => sum + Math.pow(item - avg, 2), 0) / Math.max(recent.length - 1, 1);
  return Math.sqrt(variance);
}

function inverseVolatilityWeights(volatilities) {
  const valid = volatilities.filter((item) => Number.isFinite(item) && item > 1e-9).sort((left, right) => left - right);
  const fallback = valid.length ? valid[Math.floor(valid.length / 2)] : NaN;
  const inverse = volatilities.map((volatility) => {
    const usable = Number.isFinite(volatility) && volatility > 1e-9 ? volatility : fallback;
    return Number.isFinite(usable) && usable > 1e-9 ? 1 / usable : 1;
  });
  const total = inverse.reduce((sum, item) => sum + item, 0);
  if (!Number.isFinite(total) || total <= 0) return volatilities.map(() => 1 / volatilities.length);
  return inverse.map((item) => item / total);
}

function normalizedSeries(code, range) {
  const rows = rowsInRange(code, range);
  if (rows.length < 2) return null;
  const base = rows[0].value;
  const anchor = ANCHOR_TO_SYNTHETIC && state.rangeMode === "longest" && !isSyntheticCode(code)
    ? equalWeightAnchor(rows[0].dateMs, range)
    : 100;
  let peak = -Infinity;
  const values = rows.map((row) => {
    const value = row.value / base * anchor;
    peak = Math.max(peak, row.value);
    return {
      dateMs: row.dateMs,
      value,
      drawdown: row.value / peak - 1,
    };
  });
  return { code, values, metrics: calculateMetrics(rows), rows };
}

function backgroundNormalizedSeries(range) {
  if (!SHOW_BACKGROUND || !Array.isArray(state.payload.background_series)) return null;
  const rows = state.payload.background_series.filter((row) => row.dateMs >= range.start && row.dateMs <= range.end);
  if (rows.length < 2) return null;
  const base = rows[0].value;
  if (!Number.isFinite(base) || base <= 0) return null;
  let peak = -Infinity;
  const code = state.payload.background?.code || "BACKGROUND";
  const values = rows.map((row) => {
    const value = row.value / base * 100;
    peak = Math.max(peak, row.value);
    return {
      dateMs: row.dateMs,
      value,
      drawdown: row.value / peak - 1,
    };
  });
  return { code, values, rows, background: true };
}

function renderAll() {
  if (!state.payload) return;
  const range = activeRange();
  const codes = selectedCodes();
  if (!range || !codes.length) {
    dom.metricsBody.innerHTML = `<tr><td colspan="${metricColumnCount()}">请至少选择一个有数据的标的。</td></tr>`;
    clearSvg(dom.valueChart);
    clearSvg(dom.drawdownChart);
    clearSvg(dom.barChart);
    return;
  }
  dom.start.value = fmtDate(range.start);
  dom.end.value = fmtDate(range.end);
  state.dynamicSyntheticRows = buildDynamicSyntheticRows(range);
  state.dynamicRiskParityRows = buildRiskParityRows(range);
  const series = codes.map((code) => normalizedSeries(code, range)).filter(Boolean);
  const background = backgroundNormalizedSeries(range);
  const modeText = state.rangeMode === "longest" ? LONGEST_MODE_LABEL : "共同区间";
  const baseText = state.rangeMode === "longest" ? LONGEST_BASE_TEXT : commonBaseText();
  dom.valueTitle.textContent = `${VALUE_TITLE_BASE}（${valueAxisLabel()}）`;
  dom.hint.textContent = `${modeText}：${fmtDate(range.start)} 至 ${fmtDate(range.end)}；${baseText}；已显示 ${series.length} 个标的`;
  renderLineChart(dom.valueChart, VALUE_BOX, series, "value", background);
  renderLineChart(dom.drawdownChart, DRAW_BOX, series, "drawdown");
  renderBarChart(series);
  renderMetricsTable(series);
  renderErrors();
}

function renderLineChart(svg, box, series, mode, background = null) {
  clearSvg(svg);
  const plot = box.plot;
  const width = box.width - plot.left - plot.right;
  const height = box.height - plot.top - plot.bottom;
  const renderSeries = background && mode === "value" ? [background, ...series] : series;
  const allPoints = renderSeries.flatMap((item) => item.values);
  if (!allPoints.length) return;
  const xMin = Math.min(...allPoints.map((item) => item.dateMs));
  const xMax = Math.max(...allPoints.map((item) => item.dateMs));
  const pointY = (point) => mode === "drawdown" ? point.drawdown : valueAxisY(point.value);
  let yMin;
  let yMax;
  if (mode === "drawdown") {
    yMin = Math.min(...allPoints.map((item) => item.drawdown), -0.01);
    yMax = 0;
  } else if (state.valueAxisMode === "log") {
    yMin = Math.min(...allPoints.map((item) => valueAxisY(item.value)), 1);
    yMax = Math.max(...allPoints.map((item) => valueAxisY(item.value)), 1);
    yMin = Math.max(yMin, 0.0001);
    yMax = Math.max(yMax, yMin * 1.01);
    const logMin = Math.log(yMin);
    const logMax = Math.log(yMax);
    const padding = (logMax - logMin || 1) * 0.08;
    yMin = Math.exp(logMin - padding);
    yMax = Math.exp(logMax + padding);
  } else {
    const baseline = valueAxisConfig().baseline;
    yMin = Math.min(...allPoints.map((item) => valueAxisY(item.value)), baseline);
    yMax = Math.max(...allPoints.map((item) => valueAxisY(item.value)), baseline);
    const padding = (yMax - yMin || 1) * 0.08;
    yMin = state.valueAxisMode === "multiple" ? Math.max(yMin - padding, 0) : Math.max(yMin - padding, -1);
    yMax += padding;
  }
  const xScale = (value) => plot.left + ((value - xMin) / Math.max(xMax - xMin, 1)) * width;
  const yScale = state.valueAxisMode === "log" && mode === "value"
    ? (value) => {
        const safeMin = Math.max(yMin, 0.0001);
        const safeValue = Math.max(value, 0.0001);
        return plot.top + (1 - (Math.log(safeValue) - Math.log(safeMin)) / Math.max(Math.log(yMax) - Math.log(safeMin), 1e-9)) * height;
      }
    : (value) => plot.top + (1 - (value - yMin) / Math.max(yMax - yMin, 1)) * height;
  drawGrid(svg, box, xMin, xMax, yMin, yMax, mode, yScale);
  if (mode === "value") {
    const baseline = valueAxisConfig().baseline;
    if (yMin < baseline && yMax > baseline) {
      svg.appendChild(svgEl("line", { x1: plot.left, x2: plot.left + width, y1: yScale(baseline), y2: yScale(baseline), class: "zero-line" }));
    }
  }
  if (mode === "drawdown") {
    svg.appendChild(svgEl("line", { x1: plot.left, x2: plot.left + width, y1: yScale(0), y2: yScale(0), class: "zero-line" }));
  }
  if (background && mode === "value") {
    const points = background.values.map((point) => [
      xScale(point.dateMs),
      yScale(pointY(point)),
    ]);
    const path = points.map((point, index) => `${index ? "L" : "M"}${point[0].toFixed(1)},${point[1].toFixed(1)}`).join(" ");
    svg.appendChild(svgEl("path", { d: path, class: "background-line", stroke: state.payload.background?.color || "#94A3B8" }));
    const label = svgEl("text", {
      x: plot.left + width - 4,
      y: plot.top + 16,
      "text-anchor": "end",
      class: "background-label",
    });
    label.textContent = `背景：${state.payload.background?.name || "上证指数"}`;
    svg.appendChild(label);
  }
  series.forEach((item) => {
    const instrument = instrumentByCode(item.code);
    const points = item.values.map((point) => [
      xScale(point.dateMs),
      yScale(pointY(point)),
    ]);
    const path = points.map((point, index) => `${index ? "L" : "M"}${point[0].toFixed(1)},${point[1].toFixed(1)}`).join(" ");
    svg.appendChild(svgEl("path", { d: path, class: "series-line", stroke: instrument.color }));
  });
}

function drawGrid(svg, box, xMin, xMax, yMin, yMax, mode, yScale) {
  const plot = box.plot;
  const width = box.width - plot.left - plot.right;
  const height = box.height - plot.top - plot.bottom;
  const axis = svgEl("g", { class: "axis" });
  for (let i = 0; i <= 4; i++) {
    const value = mode === "value" && state.valueAxisMode === "log"
      ? Math.exp(Math.log(yMax) - (Math.log(yMax) - Math.log(Math.max(yMin, 0.0001))) * i / 4)
      : yMax - (yMax - yMin) * i / 4;
    const y = yScale(value);
    axis.appendChild(svgEl("line", { x1: plot.left, x2: plot.left + width, y1: y, y2: y, class: "grid-line" }));
    const text = svgEl("text", { x: plot.left - 8, y: y + 4, "text-anchor": "end" });
    text.textContent = mode === "drawdown" ? `${(value * 100).toFixed(0)}%` : formatValueAxis(value);
    axis.appendChild(text);
  }
  for (let i = 0; i <= 4; i++) {
    const x = plot.left + width * i / 4;
    const dateMs = xMin + (xMax - xMin) * i / 4;
    axis.appendChild(svgEl("line", { x1: x, x2: x, y1: plot.top, y2: plot.top + height, class: "grid-line" }));
    const text = svgEl("text", { x, y: plot.top + height + 24, "text-anchor": "middle" });
    text.textContent = fmtDate(dateMs).slice(0, 7);
    axis.appendChild(text);
  }
  svg.appendChild(axis);
}

function renderBarChart(series) {
  const svg = dom.barChart;
  clearSvg(svg);
  const box = BAR_BOX;
  const plot = box.plot;
  const width = box.width - plot.left - plot.right;
  const height = box.height - plot.top - plot.bottom;
  const maxValue = Math.max(
    ...series.map((item) => Math.max(item.metrics.annualizedReturn, Math.abs(item.metrics.maxDrawdown))).filter(Number.isFinite),
    0.1
  );
  const yScale = (value) => plot.top + (1 - value / (maxValue * 1.18)) * height;
  for (let i = 0; i <= 4; i++) {
    const value = maxValue * 1.18 * i / 4;
    const y = yScale(value);
    svg.appendChild(svgEl("line", { x1: plot.left, x2: plot.left + width, y1: y, y2: y, class: "grid-line" }));
    const label = svgEl("text", { x: plot.left - 7, y: y + 4, "text-anchor": "end", class: "axis" });
    label.textContent = `${(value * 100).toFixed(0)}%`;
    svg.appendChild(label);
  }
  const groupWidth = width / Math.max(series.length, 1);
  const barWidth = Math.min(28, groupWidth * 0.28);
  series.forEach((item, index) => {
    const instrument = instrumentByCode(item.code);
    const center = plot.left + groupWidth * index + groupWidth / 2;
    const ann = Math.max(item.metrics.annualizedReturn, 0);
    const dd = Math.abs(item.metrics.maxDrawdown);
    const annY = yScale(ann);
    const ddY = yScale(dd);
    svg.appendChild(svgEl("rect", { x: center - barWidth - 2, y: annY, width: barWidth, height: plot.top + height - annY, fill: "#2E7D32" }));
    svg.appendChild(svgEl("rect", { x: center + 2, y: ddY, width: barWidth, height: plot.top + height - ddY, fill: instrument.color }));
    const annLabel = svgEl("text", { x: center - barWidth / 2 - 2, y: annY - 5, "text-anchor": "middle", class: "axis" });
    annLabel.textContent = `${(ann * 100).toFixed(1)}%`;
    svg.appendChild(annLabel);
    const ddLabel = svgEl("text", { x: center + barWidth / 2 + 2, y: ddY - 5, "text-anchor": "middle", class: "axis" });
    ddLabel.textContent = `${(dd * 100).toFixed(1)}%`;
    svg.appendChild(ddLabel);
    const name = instrument.name.replace(/ ETF|指数/g, "");
    const text = svgEl("text", { x: center, y: plot.top + height + 24, "text-anchor": "middle", class: "axis" });
    text.textContent = name.length > 8 ? name.slice(0, 8) : name;
    svg.appendChild(text);
  });
  const legend = svgEl("g", {});
  legend.appendChild(svgEl("rect", { x: plot.left, y: 0, width: 12, height: 12, fill: "#2E7D32" }));
  const annText = svgEl("text", { x: plot.left + 18, y: 11, class: "axis" });
  annText.textContent = "年化收益";
  legend.appendChild(annText);
  legend.appendChild(svgEl("rect", { x: plot.left + 94, y: 0, width: 12, height: 12, fill: "#64748B" }));
  const ddText = svgEl("text", { x: plot.left + 112, y: 11, class: "axis" });
  ddText.textContent = "最大回撤=曲线色";
  legend.appendChild(ddText);
  svg.appendChild(legend);
}

function renderMetricsTable(series) {
  dom.metricsBody.innerHTML = "";
  if (!series.length) {
    dom.metricsBody.innerHTML = `<tr><td colspan="${metricColumnCount()}">暂无可比数据。</td></tr>`;
    return;
  }
  updateSortHeaders();
  const sorted = [...series].sort(compareMetricRows);
  sorted.forEach((item) => {
    const instrument = instrumentByCode(item.code);
    const row = document.createElement("tr");
    const cells = [
      { value: instrument.name, type: "text" },
      { value: pct(item.metrics.totalReturn), type: "gain" },
      { value: pct(item.metrics.maxReturn), type: "gain" },
      { value: pct(item.metrics.annualizedReturn), type: "gain" },
      { value: pct(item.metrics.maxDrawdown), type: "loss" },
      { value: pct(item.metrics.annualizedVolatility), type: "gain" },
      { value: ratioText(item.metrics.annualizedReturnDrawdownRatio), type: "ratio" },
    ];
    if (INCLUDE_RECOVERY_METRICS) {
      cells.push(
        { value: recoveryText(item.metrics.longestRecoveryDays), type: "duration" },
        { value: pct(item.metrics.rollingThreeYearWorstReturn), type: "loss" },
      );
    }
    cells.forEach((cellData) => {
      const cell = document.createElement("td");
      const value = cellData.value;
      cell.textContent = value;
      if (cellData.type !== "text" && cellData.type !== "duration" && value !== "-") {
        const numeric = Number(value.replace("%", ""));
        if (cellData.type === "loss") cell.className = "negative";
        else if (numeric >= 0) cell.className = "positive";
        else cell.className = "negative";
      }
      row.appendChild(cell);
    });
    dom.metricsBody.appendChild(row);
  });
}

function compareMetricRows(left, right) {
  const leftInstrument = instrumentByCode(left.code);
  const rightInstrument = instrumentByCode(right.code);
  let leftValue;
  let rightValue;
  if (state.sortKey === "name") {
    leftValue = leftInstrument.name;
    rightValue = rightInstrument.name;
  } else {
    leftValue = left.metrics[state.sortKey];
    rightValue = right.metrics[state.sortKey];
  }
  let result;
  if (typeof leftValue === "string" || typeof rightValue === "string") {
    result = String(leftValue).localeCompare(String(rightValue), "zh-CN");
  } else {
    const leftNumber = Number.isFinite(leftValue) ? leftValue : -Infinity;
    const rightNumber = Number.isFinite(rightValue) ? rightValue : -Infinity;
    result = leftNumber - rightNumber;
  }
  return state.sortDirection === "asc" ? result : -result;
}

function updateSortHeaders() {
  document.querySelectorAll("th[data-sort]").forEach((header) => {
    header.classList.toggle("sorted-asc", header.dataset.sort === state.sortKey && state.sortDirection === "asc");
    header.classList.toggle("sorted-desc", header.dataset.sort === state.sortKey && state.sortDirection === "desc");
  });
}

function updateValueAxisControls() {
  dom.axisReturn.classList.toggle("secondary", state.valueAxisMode !== "return");
  dom.axisMultiple.classList.toggle("secondary", state.valueAxisMode !== "multiple");
  dom.axisLog.classList.toggle("secondary", state.valueAxisMode !== "log");
}

function setValueAxisMode(mode) {
  state.valueAxisMode = Object.prototype.hasOwnProperty.call(VALUE_AXIS_MODES, mode) ? mode : "return";
  updateValueAxisControls();
  renderAll();
}

function renderErrors() {
  const errors = state.payload.errors || [];
  dom.errorsSection.hidden = !errors.length;
  dom.errors.innerHTML = errors.map((item) => `${item.name}: ${item.error}`).join("<br>");
}

function instrumentByCode(code) {
  return state.payload.instruments.find((item) => item.code === code) || { name: code, color: "#555" };
}

function applyQuickRange(kind, value) {
  const bounds = currentBounds();
  if (!bounds) return;
  let start = bounds.start;
  let end = bounds.end;
  if (kind === "years") {
    start = Math.max(bounds.start, end - Number(value) * 365.25 * MS_DAY);
  } else if (kind === "since") {
    start = Math.max(bounds.start, parseDate(value));
  }
  setActiveRange(start, end);
}

function panActiveRange(direction, fraction = 0.35) {
  const range = activeRange();
  if (!range) return;
  const span = range.end - range.start;
  const shift = span * fraction * direction;
  setActiveRange(range.start + shift, range.end + shift);
}

function zoomActiveRange(factor) {
  const range = activeRange();
  if (!range) return;
  const center = (range.start + range.end) / 2;
  const span = Math.max((range.end - range.start) * factor, 20 * MS_DAY);
  setActiveRange(center - span / 2, center + span / 2);
}

function setRangeMode(mode) {
  state.rangeMode = mode === "longest" ? "longest" : "common";
  dom.modeCommon.classList.toggle("secondary", state.rangeMode !== "common");
  dom.modeLongest.classList.toggle("secondary", state.rangeMode !== "longest");
  setRangeToCurrentMode();
  renderAll();
}

function svgPointer(svg, event) {
  const point = svg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  return point.matrixTransform(svg.getScreenCTM().inverse());
}

function installChartPan() {
  const svg = dom.valueChart;
  svg.addEventListener("pointerdown", (event) => {
    const range = activeRange();
    if (!range) return;
    const point = svgPointer(svg, event);
    const plot = VALUE_BOX.plot;
    const plotRight = VALUE_BOX.width - plot.right;
    const plotBottom = VALUE_BOX.height - plot.bottom;
    if (point.x < plot.left || point.x > plotRight || point.y < plot.top || point.y > plotBottom) return;
    state.drag = { startX: point.x, currentX: point.x, range };
    svg.classList.add("dragging");
    svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener("pointermove", (event) => {
    if (!state.drag) return;
    const point = svgPointer(svg, event);
    const plot = VALUE_BOX.plot;
    const plotRight = VALUE_BOX.width - plot.right;
    const x = Math.max(plot.left, Math.min(plotRight, point.x));
    state.drag.currentX = x;
  });
  svg.addEventListener("pointerup", () => {
    if (!state.drag) return;
    const plot = VALUE_BOX.plot;
    const width = VALUE_BOX.width - plot.left - plot.right;
    const deltaX = state.drag.currentX - state.drag.startX;
    const range = state.drag.range;
    svg.classList.remove("dragging");
    state.drag = null;
    if (Math.abs(deltaX) < 8) return;
    const span = range.end - range.start;
    const shift = -(deltaX / Math.max(width, 1)) * span;
    setActiveRange(range.start + shift, range.end + shift);
  });
  svg.addEventListener("pointercancel", () => {
    if (!state.drag) return;
    svg.classList.remove("dragging");
    state.drag = null;
  });
}

document.querySelectorAll("[data-range]").forEach((button) => {
  button.addEventListener("click", () => applyQuickRange("all"));
});
document.querySelectorAll("[data-years]").forEach((button) => {
  button.addEventListener("click", () => applyQuickRange("years", button.dataset.years));
});
document.querySelectorAll("[data-since]").forEach((button) => {
  button.addEventListener("click", () => applyQuickRange("since", button.dataset.since));
});
document.querySelectorAll("[data-mode]").forEach((button) => {
  button.addEventListener("click", () => setRangeMode(button.dataset.mode));
});
document.querySelectorAll("[data-y-axis]").forEach((button) => {
  button.addEventListener("click", () => setValueAxisMode(button.dataset.yAxis));
});
document.querySelectorAll("th[data-sort]").forEach((header) => {
  header.addEventListener("click", () => {
    const key = header.dataset.sort;
    if (state.sortKey === key) {
      state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
    } else {
      state.sortKey = key;
      state.sortDirection = key === "name" ? "asc" : "desc";
    }
    renderAll();
  });
});
dom.start.addEventListener("change", () => { clampInputsToCurrentMode(); renderAll(); });
dom.end.addEventListener("change", () => { clampInputsToCurrentMode(); renderAll(); });
dom.panLeft.addEventListener("click", () => panActiveRange(-1));
dom.panRight.addEventListener("click", () => panActiveRange(1));
dom.zoomIn.addEventListener("click", () => zoomActiveRange(0.5));
dom.zoomOut.addEventListener("click", () => zoomActiveRange(2));
dom.reset.addEventListener("click", () => { setRangeToCurrentMode(); renderAll(); });
dom.refresh.addEventListener("click", () => loadHistory(true));
updateValueAxisControls();
installChartPan();
loadHistory(false);
</script>
</body>
</html>"""
    return _inject_unified_shell(page)


def render_index_compare_page() -> str:
    page = render_etf_compare_page()
    replacements = {
        "ETF 复权对比 - MyShortTerm": "指数对比 - MyShortTerm",
        "ETF 复权价值曲线对比": "指数总收益曲线对比",
        "日线复权口径": "指数日线口径",
        "/api/etf-compare/history.json": "/api/index-compare/history.json",
        "<body>": (
            '<body data-api-path="/api/index-compare/history.json" data-extra-metrics="true" '
            'data-synthetic-code="VIRTUAL_EQUAL_WEIGHT_INDEX" data-longest-mode-label="最早起" '
            'data-longest-base-text="后上市指数接到虚拟等权指数位置">'
        ),
        "2012起": "最早起",
        "复权价值曲线": "指数价值曲线",
        (
            "2012起模式按最早可用 ETF 开始展示；后上市 ETF 从上市日对应的虚拟等权ETF位置接上。"
            "虚拟等权ETF按 512890、510500、510300、159915 四只真实 ETF 中当日已有数据的成分动态等权；"
            "480092 为自由现金流R收益指数点位代理。"
        ): (
            "最早起模式按最早可用指数开始展示；后上市指数从上市日对应的虚拟等权指数位置接上。"
            "指数页采用 Tushare 指数日线，优先使用全收益/收益指数：红利低波全收益、"
            "中证500全收益、沪深300全收益、创业板R、自由现金流R；虚拟等权指数按当日已有数据的成分动态等权。"
        ),
        '<th data-sort="annualizedReturnDrawdownRatio">年化收益/最大回撤</th>': (
            '<th data-sort="annualizedReturnDrawdownRatio">年化收益/最大回撤</th>\n'
            '                <th data-sort="longestRecoveryDays">最长回本时间</th>\n'
            '                <th data-sort="rollingThreeYearWorstReturn">滚动3年最差收益</th>'
        ),
    }
    for old, new in replacements.items():
        page = page.replace(old, new)
    page = page.replace(
        "最早起模式按最早可用 ETF 开始展示；后上市 ETF 从上市日对应的虚拟等权ETF位置接上。"
        "虚拟等权ETF按 512890、510500、510300、159915 四只真实 ETF 中当日已有数据的成分动态等权；"
        "480092 为自由现金流R收益指数点位代理。",
        "最早起模式按最早可用指数开始展示；后上市指数从上市日对应的虚拟等权指数位置接上。"
        "指数页采用 Tushare 指数日线，优先使用全收益/收益指数：红利低波全收益、"
        "中证500全收益、沪深300全收益、创业板R、自由现金流R；虚拟等权指数按当日已有数据的成分动态等权。",
    )
    return page


def render_strategy_index_compare_page() -> str:
    page = render_etf_compare_page()
    replacements = {
        "ETF 复权对比 - MyShortTerm": "策略指数对比 - MyShortTerm",
        "ETF 复权价值曲线对比": "策略指数收益曲线对比",
        "日线复权口径": "全收益指数口径",
        "/api/etf-compare/history.json": "/api/strategy-index-compare/history.json",
        "<body>": (
            '<body data-api-path="/api/strategy-index-compare/history.json" data-extra-metrics="true" '
            'data-synthetic-code="VIRTUAL_EQUAL_WEIGHT_STRATEGY" '
            'data-risk-parity-code="VIRTUAL_RISK_PARITY_STRATEGY" data-anchor-synthetic="false" '
            'data-show-background="true" data-longest-mode-label="最早起" '
            'data-longest-base-text="当前指数自身起点=0%；上证指数作灰色背景参考">'
        ),
        (
            "2012起模式按最早可用 ETF 开始展示；后上市 ETF 从上市日对应的虚拟等权ETF位置接上。"
            "虚拟等权ETF按 512890、510500、510300、159915 四只真实 ETF 中当日已有数据的成分动态等权；"
            "480092 为自由现金流R收益指数点位代理。"
        ): (
            "最早起模式按最早可用指数开始展示。策略指数页对比国信价值全收益、创成长R、"
            "红利低波全收益、自由现金流R，并提供当前勾选成分的策略等权组合和滚动60日风险平价组合；"
            "上证指数作为灰色背景线，仅用于观察市场背景，不参与指标排序。"
        ),
        "2012起": "最早起",
        "复权价值曲线": "策略指数曲线",
        '<th data-sort="annualizedReturnDrawdownRatio">年化收益/最大回撤</th>': (
            '<th data-sort="annualizedReturnDrawdownRatio">年化收益/最大回撤</th>\n'
            '                <th data-sort="longestRecoveryDays">最长回本时间</th>\n'
            '                <th data-sort="rollingThreeYearWorstReturn">滚动3年最差收益</th>'
        ),
    }
    for old, new in replacements.items():
        page = page.replace(old, new)
    return page


def render_value_compare_page() -> str:
    return render_strategy_index_compare_page()


def render_trend_channel_page(channel: str) -> str:
    if channel == "theme":
        title = "主线指数趋势图"
        api_path = "/api/trend-channels/theme.json"
        note = "主线指数按代表性主题分组。轨道默认按 2016 年以来的对数价格统计分位拟合，短历史指数按可用区间拟合。"
    else:
        title = "宽基趋势图"
        api_path = "/api/trend-channels/broad.json"
        note = "宽基与策略指数默认用价格指数口径。轨道默认按 2016 年以来的对数价格统计分位拟合，用于观察当前位置，不作为交易指令。"
    page = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__ - MyShortTerm</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1c2430;
      --muted: #687385;
      --line: #d9dee7;
      --accent: #0f766e;
      --soft: #edf7f5;
      --bad: #b42318;
      --good: #157347;
      --warn: #a15c07;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      letter-spacing: 0;
    }
    .page-header {
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.97);
    }
    .bar {
      max-width: 1440px;
      margin: 0 auto;
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 700;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .meta {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      background: #fff;
      white-space: nowrap;
    }
    main {
      max-width: 1600px;
      margin: 0 auto;
      padding: 18px 20px 28px;
      display: grid;
      gap: 16px;
      align-items: start;
    }
    section {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }
    .panel-title {
      margin: 0;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 15px;
      font-weight: 700;
      background: #fbfcfd;
    }
    .content { padding: 14px; }
    .controls-layout {
      display: grid;
      grid-template-columns: minmax(420px, 1.35fr) minmax(260px, 0.7fr) minmax(240px, 0.8fr);
      gap: 16px;
      align-items: start;
    }
    .control-group { display: grid; gap: 10px; }
    .control-title {
      font-size: 13px;
      font-weight: 700;
      color: var(--muted);
    }
    .instrument-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 8px 14px;
    }
    .instrument {
      display: grid;
      grid-template-columns: auto 14px 1fr;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      line-height: 1.35;
    }
    .instrument small {
      display: block;
      color: var(--muted);
      font-size: 11px;
      margin-top: 1px;
    }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 2px;
      display: inline-block;
    }
    .quick-buttons, .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    button {
      border: 1px solid var(--accent);
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 650;
      padding: 7px 10px;
      cursor: pointer;
      min-height: 34px;
    }
    button.secondary {
      background: #fff;
      color: var(--accent);
    }
    button:disabled {
      cursor: wait;
      opacity: 0.65;
    }
    .note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.55;
    }
    .status {
      min-height: 20px;
      color: var(--muted);
      font-size: 13px;
    }
    .status.error { color: var(--bad); }
    .status.ok { color: var(--good); }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }
    .summary-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
      text-align: left;
      padding: 10px;
      display: grid;
      gap: 7px;
      cursor: pointer;
      min-height: 118px;
    }
    .summary-card.active {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--soft);
    }
    .card-head {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }
    .card-name {
      font-weight: 700;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .card-group {
      color: var(--muted);
      font-size: 12px;
    }
    .card-metrics {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px 10px;
      font-size: 12px;
      color: var(--muted);
    }
    .card-metrics strong {
      display: block;
      color: var(--text);
      font-size: 14px;
      margin-top: 2px;
    }
    .tag {
      display: inline-flex;
      width: fit-content;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      background: #eef2ff;
      color: #3730a3;
    }
    .tag.low { background: #ecfdf3; color: var(--good); }
    .tag.high { background: #fff7ed; color: var(--warn); }
    .tag.break { background: #fef3f2; color: var(--bad); }
    .chart-wrap {
      padding: 12px 14px 14px;
    }
    .chart-head {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      margin-bottom: 8px;
      flex-wrap: wrap;
    }
    .chart-title {
      font-size: 15px;
      font-weight: 700;
    }
    .chart-meta {
      color: var(--muted);
      font-size: 12px;
    }
    svg {
      width: 100%;
      height: auto;
      display: block;
      overflow: visible;
    }
    .trend-chart svg { min-height: 430px; }
    .drawdown-chart svg { min-height: 165px; }
    .axis text, text.axis {
      fill: var(--muted);
      font-size: 12px;
    }
    .axis line, .grid-line {
      stroke: #e8ebf0;
      stroke-width: 1;
    }
    .zero-line {
      stroke: #9aa3af;
      stroke-width: 1;
    }
    .price-line {
      fill: none;
      stroke-width: 2.6;
      stroke-linejoin: round;
      stroke-linecap: round;
    }
    .trend-line {
      fill: none;
      stroke: #111827;
      stroke-width: 1.8;
      stroke-dasharray: 6 5;
    }
    .band-line {
      fill: none;
      stroke: #64748b;
      stroke-width: 1.2;
      stroke-dasharray: 4 5;
    }
    .drawdown-line {
      fill: none;
      stroke-width: 2.2;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px 9px;
      text-align: right;
      white-space: nowrap;
    }
    th:first-child, td:first-child,
    th:nth-child(2), td:nth-child(2) {
      text-align: left;
      white-space: normal;
    }
    th {
      color: var(--muted);
      font-weight: 650;
      background: #fbfcfd;
    }
    tbody tr {
      cursor: pointer;
    }
    tbody tr.active {
      background: var(--soft);
    }
    .positive { color: var(--good); font-weight: 650; }
    .negative { color: var(--bad); font-weight: 650; }
    .empty {
      color: var(--muted);
      padding: 12px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }
    @media (max-width: 980px) {
      .bar { align-items: flex-start; flex-direction: column; }
      .meta { justify-content: flex-start; }
      .controls-layout { grid-template-columns: 1fr; }
      th, td { white-space: normal; }
    }
  </style>
</head>
<body data-channel="__CHANNEL__" data-api-path="__API_PATH__">
  __MYINVEST_HEADER__
  <div class="page-header">
    <div class="bar">
      <h1>__TITLE__</h1>
      <div class="meta">
        <a class="pill" href="/">返回面板</a>
        <a class="pill" href="/broad-trend">宽基趋势图</a>
        <a class="pill" href="/theme-trend">主线指数趋势图</a>
        <span class="pill">统计轨道</span>
      </div>
    </div>
  </div>
  <main>
    <section>
      <h2 class="panel-title">趋势设置</h2>
      <div class="content controls-layout">
        <div class="control-group">
          <div class="control-title">指数</div>
          <div id="instrument-list" class="instrument-list"></div>
        </div>
        <div class="control-group">
          <div class="control-title">轨道口径</div>
          <div class="quick-buttons">
            <button id="fit-since2016" type="button" data-fit="since2016">2016年以来</button>
            <button id="fit-all" type="button" class="secondary" data-fit="all">全历史</button>
          </div>
          <div class="note">__NOTE__</div>
        </div>
        <div class="control-group">
          <div class="control-title">操作</div>
          <div class="actions">
            <button id="refresh-data" type="button">更新数据</button>
          </div>
          <div id="status" class="status">准备加载数据...</div>
        </div>
      </div>
    </section>
    <section>
      <h2 class="panel-title">当前位置</h2>
      <div id="summary-grid" class="content summary-grid"></div>
    </section>
    <section class="trend-chart">
      <div class="chart-wrap">
        <div class="chart-head">
          <div id="trend-title" class="chart-title">趋势轨道</div>
          <div id="trend-meta" class="chart-meta">-</div>
        </div>
        <svg id="trend-chart" viewBox="0 0 1000 430" role="img" aria-label="趋势轨道图"></svg>
      </div>
    </section>
    <section class="drawdown-chart">
      <div class="chart-wrap">
        <div class="chart-head">
          <div class="chart-title">回撤曲线</div>
          <div class="chart-meta">当前指数相对历史高点的跌幅</div>
        </div>
        <svg id="drawdown-chart" viewBox="0 0 1000 165" role="img" aria-label="回撤曲线"></svg>
      </div>
    </section>
    <section>
      <h2 class="panel-title">轨道指标</h2>
      <div class="content">
        <table>
          <thead>
            <tr>
              <th>指数</th>
              <th>分组</th>
              <th>日期</th>
              <th>最新</th>
              <th>回撤</th>
              <th>轨道位置</th>
              <th>距下轨</th>
              <th>距中轨</th>
              <th>距上轨</th>
              <th>趋势年化</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody id="metrics-body"></tbody>
        </table>
      </div>
    </section>
    <section id="errors-section" hidden>
      <h2 class="panel-title">数据提示</h2>
      <div id="errors" class="content note"></div>
    </section>
  </main>
  __MYINVEST_FOOTER__
<script>
const API_PATH = document.body.dataset.apiPath;
const MS_DAY = 24 * 60 * 60 * 1000;
const TREND_BOX = { width: 1000, height: 430, plot: { left: 64, right: 24, top: 24, bottom: 38 } };
const DRAW_BOX = { width: 1000, height: 165, plot: { left: 64, right: 24, top: 14, bottom: 30 } };
const state = {
  payload: null,
  selected: null,
  fit: "since2016",
};
const dom = {
  instruments: document.getElementById("instrument-list"),
  status: document.getElementById("status"),
  refresh: document.getElementById("refresh-data"),
  fitSince2016: document.getElementById("fit-since2016"),
  fitAll: document.getElementById("fit-all"),
  summaryGrid: document.getElementById("summary-grid"),
  trendTitle: document.getElementById("trend-title"),
  trendMeta: document.getElementById("trend-meta"),
  trendChart: document.getElementById("trend-chart"),
  drawdownChart: document.getElementById("drawdown-chart"),
  metricsBody: document.getElementById("metrics-body"),
  errorsSection: document.getElementById("errors-section"),
  errors: document.getElementById("errors"),
};

function setStatus(text, kind = "") {
  dom.status.textContent = text;
  dom.status.className = `status ${kind}`.trim();
}

function parseDate(value) {
  return new Date(`${value}T00:00:00+08:00`).getTime();
}

function fmtDate(ms) {
  const d = new Date(ms);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function pct(value) {
  if (!Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(2)}%`;
}

function signedPct(value) {
  if (!Number.isFinite(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function numberText(value) {
  if (!Number.isFinite(value)) return "-";
  if (Math.abs(value) >= 1000) return value.toFixed(1);
  return value.toFixed(2);
}

function positionText(value) {
  if (!Number.isFinite(value)) return "-";
  return value.toFixed(2);
}

function svgEl(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, String(value));
  }
  return node;
}

function clearSvg(svg) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
}

function instrumentByCode(code) {
  return state.payload?.instruments.find((item) => item.code === code);
}

function summaryByCode(code) {
  return state.payload?.summaries?.[code];
}

function rowsByCode(code) {
  return state.payload?.series?.[code] || [];
}

async function loadHistory(refresh = false) {
  dom.refresh.disabled = true;
  setStatus(refresh ? "正在更新历史数据..." : "正在加载历史数据...");
  try {
    const sep = API_PATH.includes("?") ? "&" : "?";
    const response = await fetch(`${API_PATH}${sep}fit=${state.fit}${refresh ? "&refresh=1" : ""}`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "历史数据加载失败");
    }
    for (const rows of Object.values(payload.series)) {
      rows.forEach((row) => {
        row.dateMs = parseDate(row.date);
        row.close = Number(row.close);
        row.trend = Number(row.trend);
        row.lower = Number(row.lower);
        row.upper = Number(row.upper);
        row.drawdown = Number(row.drawdown);
        row.channelPosition = Number(row.channelPosition);
      });
    }
    state.payload = payload;
    if (!state.selected || !payload.series[state.selected]?.length) {
      const first = payload.instruments.find((item) => payload.series[item.code]?.length);
      state.selected = first ? first.code : null;
    }
    renderInstrumentControls();
    updateFitButtons();
    renderAll();
    setStatus(refresh ? "数据已更新" : "数据已加载", "ok");
  } catch (error) {
    setStatus(`失败：${error.message}`, "error");
  } finally {
    dom.refresh.disabled = false;
  }
}

function renderInstrumentControls() {
  dom.instruments.innerHTML = "";
  state.payload.instruments.forEach((item) => {
    const hasData = Boolean(state.payload.series[item.code]?.length);
    const label = document.createElement("label");
    label.className = "instrument";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "trend-instrument";
    input.value = item.code;
    input.checked = state.selected === item.code;
    input.disabled = !hasData;
    input.addEventListener("change", () => {
      state.selected = item.code;
      renderAll();
    });
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = item.color;
    const text = document.createElement("span");
    text.textContent = hasData ? item.name : `${item.name}（无数据）`;
    const group = document.createElement("small");
    group.textContent = `${item.group} · ${item.code}`;
    text.appendChild(group);
    label.append(input, swatch, text);
    dom.instruments.appendChild(label);
  });
}

function renderAll() {
  renderSummaryCards();
  renderTrendChart();
  renderDrawdownChart();
  renderMetricsTable();
  renderErrors();
}

function renderSummaryCards() {
  dom.summaryGrid.innerHTML = "";
  const items = state.payload.instruments
    .filter((item) => state.payload.summaries[item.code])
    .sort((left, right) => {
      const groupCompare = left.group.localeCompare(right.group, "zh-CN");
      if (groupCompare) return groupCompare;
      return (summaryByCode(left.code).channelPosition || 0) - (summaryByCode(right.code).channelPosition || 0);
    });
  if (!items.length) {
    dom.summaryGrid.innerHTML = '<div class="empty">暂无趋势数据。</div>';
    return;
  }
  items.forEach((item) => {
    const summary = summaryByCode(item.code);
    const card = document.createElement("button");
    card.type = "button";
    card.className = `summary-card${state.selected === item.code ? " active" : ""}`;
    card.addEventListener("click", () => {
      state.selected = item.code;
      renderInstrumentControls();
      renderAll();
    });
    const tagClass = statusClass(summary.status);
    card.innerHTML = `
      <div class="card-head"><span class="swatch" style="background:${item.color}"></span><span class="card-name">${escapeHtml(item.name)}</span></div>
      <div class="card-group">${escapeHtml(item.group)}</div>
      <span class="tag ${tagClass}">${escapeHtml(summary.status)}</span>
      <div class="card-metrics">
        <span>回撤<strong>${pct(summary.drawdown)}</strong></span>
        <span>轨道位置<strong>${positionText(summary.channelPosition)}</strong></span>
        <span>距下轨<strong>${signedPct(summary.distanceToLower)}</strong></span>
        <span>趋势年化<strong>${pct(summary.annualizedTrend)}</strong></span>
      </div>
    `;
    dom.summaryGrid.appendChild(card);
  });
}

function renderTrendChart() {
  const svg = dom.trendChart;
  clearSvg(svg);
  const rows = rowsByCode(state.selected);
  const instrument = instrumentByCode(state.selected);
  const summary = summaryByCode(state.selected);
  if (!rows.length || !instrument || !summary) {
    dom.trendTitle.textContent = "趋势轨道";
    dom.trendMeta.textContent = "-";
    return;
  }
  dom.trendTitle.textContent = `${instrument.name} 趋势轨道`;
  dom.trendMeta.textContent = `${state.payload.fit_label}：${summary.startDate} 至 ${summary.endDate}；${summary.status}`;
  const box = TREND_BOX;
  const plot = box.plot;
  const width = box.width - plot.left - plot.right;
  const height = box.height - plot.top - plot.bottom;
  const xMin = rows[0].dateMs;
  const xMax = rows[rows.length - 1].dateMs;
  const positiveValues = rows.flatMap((row) => [row.close, row.trend, row.lower, row.upper]).filter((value) => value > 0);
  let yMin = Math.min(...positiveValues);
  let yMax = Math.max(...positiveValues);
  const logMin = Math.log(yMin);
  const logMax = Math.log(yMax);
  const padding = (logMax - logMin || 1) * 0.08;
  yMin = Math.exp(logMin - padding);
  yMax = Math.exp(logMax + padding);
  const xScale = (value) => plot.left + ((value - xMin) / Math.max(xMax - xMin, 1)) * width;
  const yScale = (value) => {
    const safe = Math.max(value, 0.000001);
    return plot.top + (1 - (Math.log(safe) - Math.log(yMin)) / Math.max(Math.log(yMax) - Math.log(yMin), 1e-9)) * height;
  };
  drawTrendGrid(svg, box, xMin, xMax, yMin, yMax, yScale);
  const upperPoints = rows.map((row) => [xScale(row.dateMs), yScale(row.upper)]);
  const lowerPoints = rows.map((row) => [xScale(row.dateMs), yScale(row.lower)]).reverse();
  const bandPath = [...upperPoints, ...lowerPoints]
    .map((point, index) => `${index ? "L" : "M"}${point[0].toFixed(1)},${point[1].toFixed(1)}`)
    .join(" ") + " Z";
  svg.appendChild(svgEl("path", { d: bandPath, fill: instrument.color, opacity: "0.10" }));
  svg.appendChild(pathFor(rows, "upper", xScale, yScale, { class: "band-line" }));
  svg.appendChild(pathFor(rows, "lower", xScale, yScale, { class: "band-line" }));
  svg.appendChild(pathFor(rows, "trend", xScale, yScale, { class: "trend-line" }));
  svg.appendChild(pathFor(rows, "close", xScale, yScale, { class: "price-line", stroke: instrument.color }));
  const latest = rows[rows.length - 1];
  svg.appendChild(svgEl("circle", { cx: xScale(latest.dateMs), cy: yScale(latest.close), r: 4, fill: instrument.color }));
  const label = svgEl("text", { x: xScale(latest.dateMs) - 8, y: yScale(latest.close) - 10, "text-anchor": "end", class: "axis" });
  label.textContent = numberText(latest.close);
  svg.appendChild(label);
  drawLegend(svg, plot.left, instrument.color);
}

function renderDrawdownChart() {
  const svg = dom.drawdownChart;
  clearSvg(svg);
  const rows = rowsByCode(state.selected);
  const instrument = instrumentByCode(state.selected);
  if (!rows.length || !instrument) return;
  const box = DRAW_BOX;
  const plot = box.plot;
  const width = box.width - plot.left - plot.right;
  const height = box.height - plot.top - plot.bottom;
  const xMin = rows[0].dateMs;
  const xMax = rows[rows.length - 1].dateMs;
  const yMin = Math.min(...rows.map((row) => row.drawdown), -0.01);
  const yMax = 0;
  const xScale = (value) => plot.left + ((value - xMin) / Math.max(xMax - xMin, 1)) * width;
  const yScale = (value) => plot.top + (1 - (value - yMin) / Math.max(yMax - yMin, 1)) * height;
  drawDrawdownGrid(svg, box, xMin, xMax, yMin, yMax, yScale);
  svg.appendChild(svgEl("line", { x1: plot.left, x2: plot.left + width, y1: yScale(0), y2: yScale(0), class: "zero-line" }));
  svg.appendChild(pathFor(rows, "drawdown", xScale, yScale, { class: "drawdown-line", stroke: instrument.color }));
}

function pathFor(rows, key, xScale, yScale, attrs) {
  const path = rows
    .map((row, index) => `${index ? "L" : "M"}${xScale(row.dateMs).toFixed(1)},${yScale(row[key]).toFixed(1)}`)
    .join(" ");
  return svgEl("path", { d: path, ...attrs });
}

function drawTrendGrid(svg, box, xMin, xMax, yMin, yMax, yScale) {
  const plot = box.plot;
  const width = box.width - plot.left - plot.right;
  const height = box.height - plot.top - plot.bottom;
  const axis = svgEl("g", { class: "axis" });
  for (let i = 0; i <= 4; i++) {
    const value = Math.exp(Math.log(yMax) - (Math.log(yMax) - Math.log(yMin)) * i / 4);
    const y = yScale(value);
    axis.appendChild(svgEl("line", { x1: plot.left, x2: plot.left + width, y1: y, y2: y, class: "grid-line" }));
    const text = svgEl("text", { x: plot.left - 8, y: y + 4, "text-anchor": "end" });
    text.textContent = numberText(value);
    axis.appendChild(text);
  }
  drawDateGrid(axis, plot, width, height, xMin, xMax);
  svg.appendChild(axis);
}

function drawDrawdownGrid(svg, box, xMin, xMax, yMin, yMax, yScale) {
  const plot = box.plot;
  const width = box.width - plot.left - plot.right;
  const height = box.height - plot.top - plot.bottom;
  const axis = svgEl("g", { class: "axis" });
  for (let i = 0; i <= 4; i++) {
    const value = yMax - (yMax - yMin) * i / 4;
    const y = yScale(value);
    axis.appendChild(svgEl("line", { x1: plot.left, x2: plot.left + width, y1: y, y2: y, class: "grid-line" }));
    const text = svgEl("text", { x: plot.left - 8, y: y + 4, "text-anchor": "end" });
    text.textContent = `${(value * 100).toFixed(0)}%`;
    axis.appendChild(text);
  }
  drawDateGrid(axis, plot, width, height, xMin, xMax);
  svg.appendChild(axis);
}

function drawDateGrid(axis, plot, width, height, xMin, xMax) {
  for (let i = 0; i <= 4; i++) {
    const x = plot.left + width * i / 4;
    const dateMs = xMin + (xMax - xMin) * i / 4;
    axis.appendChild(svgEl("line", { x1: x, x2: x, y1: plot.top, y2: plot.top + height, class: "grid-line" }));
    const text = svgEl("text", { x, y: plot.top + height + 24, "text-anchor": "middle" });
    text.textContent = fmtDate(dateMs).slice(0, 7);
    axis.appendChild(text);
  }
}

function drawLegend(svg, x, color) {
  const items = [
    ["指数点位", color, ""],
    ["趋势中枢", "#111827", "6 5"],
    ["上下轨", "#64748b", "4 5"],
  ];
  const group = svgEl("g", {});
  items.forEach((item, index) => {
    const x0 = x + index * 102;
    group.appendChild(svgEl("line", { x1: x0, x2: x0 + 22, y1: 8, y2: 8, stroke: item[1], "stroke-width": 2, "stroke-dasharray": item[2] }));
    const text = svgEl("text", { x: x0 + 28, y: 12, class: "axis" });
    text.textContent = item[0];
    group.appendChild(text);
  });
  svg.appendChild(group);
}

function renderMetricsTable() {
  dom.metricsBody.innerHTML = "";
  const rows = state.payload.instruments
    .filter((item) => state.payload.summaries[item.code])
    .map((item) => ({ instrument: item, summary: summaryByCode(item.code) }))
    .sort((left, right) => (left.summary.channelPosition || 0) - (right.summary.channelPosition || 0));
  if (!rows.length) {
    dom.metricsBody.innerHTML = '<tr><td colspan="11">暂无趋势数据。</td></tr>';
    return;
  }
  rows.forEach(({ instrument, summary }) => {
    const row = document.createElement("tr");
    if (instrument.code === state.selected) row.className = "active";
    row.addEventListener("click", () => {
      state.selected = instrument.code;
      renderInstrumentControls();
      renderAll();
    });
    const cells = [
      instrument.name,
      instrument.group,
      summary.latestDate,
      numberText(summary.close),
      pct(summary.drawdown),
      positionText(summary.channelPosition),
      signedPct(summary.distanceToLower),
      signedPct(summary.distanceToTrend),
      signedPct(summary.distanceToUpper),
      pct(summary.annualizedTrend),
      summary.status,
    ];
    cells.forEach((value, index) => {
      const td = document.createElement("td");
      td.textContent = value;
      if ([4, 6, 7, 8].includes(index)) td.className = String(value).startsWith("-") ? "negative" : "positive";
      row.appendChild(td);
    });
    dom.metricsBody.appendChild(row);
  });
}

function renderErrors() {
  const errors = state.payload?.errors || [];
  dom.errorsSection.hidden = !errors.length;
  if (!errors.length) {
    dom.errors.innerHTML = "";
    return;
  }
  dom.errors.innerHTML = errors
    .map((item) => `<div>${escapeHtml(item.code)} ${escapeHtml(item.name)}：${escapeHtml(item.error)}</div>`)
    .join("");
}

function statusClass(status) {
  if (status === "跌破下轨") return "break";
  if (status === "下轨附近") return "low";
  if (status === "上轨附近" || status === "突破上轨") return "high";
  return "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function updateFitButtons() {
  for (const button of [dom.fitSince2016, dom.fitAll]) {
    const active = button.dataset.fit === state.fit;
    button.classList.toggle("secondary", !active);
  }
}

dom.refresh.addEventListener("click", () => loadHistory(true));
for (const button of [dom.fitSince2016, dom.fitAll]) {
  button.addEventListener("click", () => {
    state.fit = button.dataset.fit;
    updateFitButtons();
    loadHistory(false);
  });
}
loadHistory(false);
</script>
</body>
</html>"""
    return (
        _inject_unified_shell(page)
        .replace("__TITLE__", html.escape(title))
        .replace("__CHANNEL__", html.escape(channel))
        .replace("__API_PATH__", html.escape(api_path))
        .replace("__NOTE__", html.escape(note))
    )


def render_capital_migration_page() -> str:
    page = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>资金迁移雷达 - MyShortTerm</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1c2430;
      --muted: #687385;
      --line: #d9dee7;
      --accent: #0f766e;
      --accent-soft: #e7f5f1;
      --bad: #b42318;
      --good: #157347;
      --warn: #a15c07;
      --ink: #111827;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      letter-spacing: 0;
    }
    .page-header {
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.97);
    }
    .bar {
      max-width: 1560px;
      margin: 0 auto;
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 700;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .meta {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      background: #fff;
      white-space: nowrap;
    }
    main {
      max-width: 1560px;
      margin: 0 auto;
      padding: 18px 20px 28px;
      display: grid;
      gap: 16px;
    }
    section {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }
    .panel-title {
      margin: 0;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 15px;
      font-weight: 700;
      background: #fbfcfd;
    }
    .content { padding: 14px; }
    .controls {
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 14px;
      align-items: center;
    }
    .control-title {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }
    .window-buttons, .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }
    button {
      border: 1px solid var(--accent);
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 650;
      padding: 7px 10px;
      cursor: pointer;
      min-height: 34px;
    }
    button.secondary {
      background: #fff;
      color: var(--accent);
    }
    button:disabled {
      cursor: wait;
      opacity: 0.65;
    }
    .status-line {
      color: var(--muted);
      font-size: 13px;
      margin-top: 8px;
    }
    .status-line.error { color: var(--bad); }
    .status-line.ok { color: var(--good); }
    .overview {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
      min-height: 76px;
    }
    .metric .label {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }
    .metric .value {
      font-size: 18px;
      font-weight: 750;
      line-height: 1.25;
    }
    .metric .small {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      margin-top: 4px;
    }
    .bucket-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 10px;
    }
    .bucket {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px;
      background: #fff;
      display: grid;
      gap: 9px;
      min-height: 170px;
    }
    .bucket-head {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
    }
    .bucket-name {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      font-weight: 750;
    }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 2px;
      display: inline-block;
      flex: 0 0 auto;
    }
    .tag {
      display: inline-flex;
      width: fit-content;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      background: #eef2ff;
      color: #3730a3;
      white-space: nowrap;
    }
    .tag.good { background: #ecfdf3; color: var(--good); }
    .tag.warn { background: #fff7ed; color: var(--warn); }
    .tag.bad { background: #fef3f2; color: var(--bad); }
    .bar-line {
      display: grid;
      gap: 4px;
    }
    .bar-meta {
      display: flex;
      justify-content: space-between;
      color: var(--muted);
      font-size: 12px;
      gap: 8px;
    }
    .bar-track {
      height: 8px;
      border-radius: 999px;
      background: #edf0f4;
      overflow: hidden;
    }
    .bar-fill {
      height: 100%;
      border-radius: 999px;
      min-width: 1px;
    }
    .bar-fill.pressure { background: #c2410c; }
    .bar-fill.absorption { background: var(--accent); }
    .bucket-stats {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px 10px;
      color: var(--muted);
      font-size: 12px;
    }
    .bucket-stats strong {
      display: block;
      color: var(--text);
      font-size: 14px;
      margin-top: 2px;
    }
    .split {
      display: grid;
      grid-template-columns: minmax(360px, 0.9fr) minmax(560px, 1.1fr);
      gap: 16px;
      align-items: start;
    }
    .flow-list {
      display: grid;
      gap: 8px;
    }
    .flow-row {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 10px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
      background: #fff;
    }
    .flow-path {
      font-weight: 700;
      min-width: 0;
    }
    .flow-meta {
      color: var(--muted);
      font-size: 12px;
      margin-top: 3px;
    }
    .flow-score {
      font-size: 18px;
      font-weight: 780;
      color: var(--ink);
      text-align: right;
    }
    .matrix-wrap {
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px 9px;
      text-align: right;
      white-space: nowrap;
    }
    th:first-child, td:first-child {
      text-align: left;
      white-space: normal;
    }
    th {
      color: var(--muted);
      font-weight: 650;
      background: #fbfcfd;
    }
    .matrix-cell {
      color: var(--ink);
      font-weight: 700;
      min-width: 82px;
    }
    .positive { color: var(--good); font-weight: 650; }
    .negative { color: var(--bad); font-weight: 650; }
    .muted { color: var(--muted); }
    .chart-wrap {
      padding: 12px 14px 14px;
    }
    .chart-head {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      margin-bottom: 8px;
      flex-wrap: wrap;
    }
    .chart-title {
      font-size: 15px;
      font-weight: 700;
    }
    .chart-meta {
      color: var(--muted);
      font-size: 12px;
    }
    svg {
      width: 100%;
      height: auto;
      display: block;
      overflow: visible;
      min-height: 320px;
    }
    .axis text, text.axis {
      fill: var(--muted);
      font-size: 12px;
    }
    .grid-line {
      stroke: #e8ebf0;
      stroke-width: 1;
    }
    .zero-line {
      stroke: #9aa3af;
      stroke-width: 1;
    }
    .series-line {
      fill: none;
      stroke-width: 2.4;
      stroke-linejoin: round;
      stroke-linecap: round;
    }
    .empty {
      color: var(--muted);
      padding: 12px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }
    .note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.55;
    }
    @media (max-width: 980px) {
      .bar, .controls { align-items: flex-start; grid-template-columns: 1fr; }
      .bar { flex-direction: column; }
      .meta, .window-buttons, .actions { justify-content: flex-start; }
      .overview { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .split { grid-template-columns: 1fr; }
      th, td { white-space: normal; }
    }
    @media (max-width: 640px) {
      .overview { grid-template-columns: 1fr; }
      .bucket-stats { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body data-api-path="__API_PATH__">
  __MYINVEST_HEADER__
  <div class="page-header">
    <div class="bar">
      <h1>资金迁移雷达</h1>
      <div class="meta">
        <a class="pill" href="/">返回面板</a>
        <a class="pill" href="/broad-trend">宽基趋势图</a>
        <a class="pill" href="/theme-trend">主线指数趋势图</a>
        <span class="pill">价量承接代理</span>
      </div>
    </div>
  </div>
  <main>
    <section>
      <h2 class="panel-title">雷达设置</h2>
      <div class="content">
        <div class="controls">
          <div>
            <div class="control-title">按交易日窗口计算流出压力、承接强度和迁移矩阵。</div>
            <div id="status" class="status-line">准备加载数据...</div>
          </div>
          <div class="window-buttons" aria-label="窗口">
            <button type="button" data-window="3" class="secondary">3日</button>
            <button type="button" data-window="5">5日</button>
            <button type="button" data-window="10" class="secondary">10日</button>
            <button type="button" data-window="20" class="secondary">20日</button>
          </div>
          <div class="actions">
            <button id="refresh-data" type="button">更新数据</button>
          </div>
        </div>
      </div>
    </section>
    <section>
      <h2 class="panel-title">状态概览</h2>
      <div id="overview" class="content overview"></div>
    </section>
    <section>
      <h2 class="panel-title">六大方向</h2>
      <div id="bucket-grid" class="content bucket-grid"></div>
    </section>
    <div class="split">
      <section>
        <h2 class="panel-title">承接路径</h2>
        <div id="flow-list" class="content flow-list"></div>
      </section>
      <section>
        <h2 class="panel-title">迁移矩阵</h2>
        <div id="matrix" class="content matrix-wrap"></div>
      </section>
    </div>
    <section>
      <div class="chart-wrap">
        <div class="chart-head">
          <div class="chart-title">相对强弱曲线</div>
          <div id="chart-meta" class="chart-meta">-</div>
        </div>
        <svg id="relative-chart" viewBox="0 0 1000 320" role="img" aria-label="方向相对强弱曲线"></svg>
      </div>
    </section>
    <section>
      <h2 class="panel-title">承接候选</h2>
      <div class="content">
        <table>
          <thead>
            <tr>
              <th>标的</th>
              <th>方向</th>
              <th>窗口收益</th>
              <th>相对收益</th>
              <th>成交活跃</th>
              <th>流出压力</th>
              <th>承接强度</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody id="leaders-body"></tbody>
        </table>
      </div>
    </section>
    <section id="errors-section" hidden>
      <h2 class="panel-title">数据提示</h2>
      <div id="errors" class="content note"></div>
    </section>
  </main>
  __MYINVEST_FOOTER__
<script>
const API_PATH = document.body.dataset.apiPath;
const BOX = { width: 1000, height: 320, plot: { left: 64, right: 24, top: 18, bottom: 36 } };
const state = { payload: null, window: 5 };
const dom = {
  status: document.getElementById("status"),
  refresh: document.getElementById("refresh-data"),
  buttons: Array.from(document.querySelectorAll("[data-window]")),
  overview: document.getElementById("overview"),
  bucketGrid: document.getElementById("bucket-grid"),
  flowList: document.getElementById("flow-list"),
  matrix: document.getElementById("matrix"),
  chart: document.getElementById("relative-chart"),
  chartMeta: document.getElementById("chart-meta"),
  leadersBody: document.getElementById("leaders-body"),
  errorsSection: document.getElementById("errors-section"),
  errors: document.getElementById("errors"),
};

function setStatus(text, kind = "") {
  dom.status.textContent = text;
  dom.status.className = `status-line ${kind}`.trim();
}

async function loadRadar(refresh = false) {
  dom.refresh.disabled = true;
  setStatus(refresh ? "正在更新数据..." : "正在加载数据...");
  try {
    const response = await fetch(`${API_PATH}?window=${state.window}${refresh ? "&refresh=1" : ""}`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "数据加载失败");
    state.payload = payload;
    renderAll();
    setStatus(refresh ? "数据已更新" : "数据已加载", "ok");
  } catch (error) {
    setStatus(`失败：${error.message}`, "error");
  } finally {
    dom.refresh.disabled = false;
  }
}

function renderAll() {
  updateWindowButtons();
  renderOverview();
  renderBuckets();
  renderFlows();
  renderMatrix();
  renderChart();
  renderLeaders();
  renderErrors();
}

function updateWindowButtons() {
  for (const button of dom.buttons) {
    button.classList.toggle("secondary", Number(button.dataset.window) !== state.window);
  }
}

function renderOverview() {
  const payload = state.payload;
  const topFlow = payload.flows[0];
  dom.overview.innerHTML = [
    metricHtml("风格状态", payload.style_status, topFlow ? `${topFlow.sourceName} -> ${topFlow.targetName}` : "暂无高分路径"),
    metricHtml("最新交易日", payload.latest_date || "-", `窗口：${payload.window} 个交易日`),
    metricHtml("基准", payload.benchmark || "-", "相对收益基准"),
    metricHtml("数据口径", "价量代理", payload.proxy_note),
  ].join("");
}

function metricHtml(label, value, detail) {
  return `<div class="metric"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div><div class="small">${escapeHtml(detail || "")}</div></div>`;
}

function renderBuckets() {
  const payload = state.payload;
  dom.bucketGrid.innerHTML = "";
  for (const bucket of payload.buckets) {
    const metric = payload.bucket_metrics[bucket.key];
    if (!metric) continue;
    const node = document.createElement("div");
    node.className = "bucket";
    node.innerHTML = `
      <div class="bucket-head">
        <div class="bucket-name"><span class="swatch" style="background:${bucket.color}"></span><span>${escapeHtml(bucket.name)}</span></div>
        <span class="tag ${tagClass(metric.status)}">${escapeHtml(metric.status)}</span>
      </div>
      ${scoreBar("流出压力", metric.outflowPressure, "pressure")}
      ${scoreBar("承接强度", metric.absorptionScore, "absorption")}
      <div class="bucket-stats">
        <span>窗口收益<strong class="${numberClass(metric.activeReturn)}">${signedPct(metric.activeReturn)}</strong></span>
        <span>相对收益<strong class="${numberClass(metric.activeRelativeReturn)}">${signedPct(metric.activeRelativeReturn)}</strong></span>
        <span>20日回撤<strong class="${numberClass(metric.drawdown20)}">${signedPct(metric.drawdown20)}</strong></span>
        <span>成交活跃<strong>${ratioText(metric.amountRatio)}</strong></span>
      </div>
    `;
    dom.bucketGrid.appendChild(node);
  }
}

function scoreBar(label, value, kind) {
  const score = Number(value || 0);
  return `
    <div class="bar-line">
      <div class="bar-meta"><span>${label}</span><strong>${score.toFixed(1)}</strong></div>
      <div class="bar-track"><div class="bar-fill ${kind}" style="width:${Math.max(1, Math.min(100, score))}%"></div></div>
    </div>
  `;
}

function renderFlows() {
  const flows = state.payload.flows;
  if (!flows.length) {
    dom.flowList.innerHTML = `<div class="empty">暂无迁移分数超过 30 的路径。</div>`;
    return;
  }
  dom.flowList.innerHTML = flows.slice(0, 8).map((flow) => `
    <div class="flow-row">
      <div>
        <div class="flow-path">${escapeHtml(flow.sourceName)} -> ${escapeHtml(flow.targetName)}</div>
        <div class="flow-meta">源流出 ${scoreText(flow.sourcePressure)} · 目标承接 ${scoreText(flow.targetAbsorption)} · ${escapeHtml(flow.label)}</div>
      </div>
      <div class="flow-score">${scoreText(flow.score)}</div>
    </div>
  `).join("");
}

function renderMatrix() {
  const payload = state.payload;
  const buckets = payload.buckets.filter((bucket) => payload.bucket_metrics[bucket.key]);
  const byPair = new Map(payload.matrix.map((row) => [`${row.source}|${row.target}`, row]));
  const head = `<tr><th>流出 \\ 承接</th>${buckets.map((bucket) => `<th>${escapeHtml(bucket.name)}</th>`).join("")}</tr>`;
  const rows = buckets.map((source) => {
    const cells = buckets.map((target) => {
      if (source.key === target.key) return `<td class="muted">-</td>`;
      const item = byPair.get(`${source.key}|${target.key}`);
      const score = item ? Number(item.score || 0) : 0;
      const opacity = Math.max(0, Math.min(0.78, score / 100));
      return `<td class="matrix-cell" style="background:rgba(15,118,110,${opacity.toFixed(2)})">${score ? score.toFixed(1) : ""}</td>`;
    }).join("");
    return `<tr><td>${escapeHtml(source.name)}</td>${cells}</tr>`;
  }).join("");
  dom.matrix.innerHTML = `<table><thead>${head}</thead><tbody>${rows}</tbody></table>`;
}

function renderLeaders() {
  const leaders = state.payload.leaders || [];
  if (!leaders.length) {
    dom.leadersBody.innerHTML = `<tr><td colspan="8">暂无承接候选。</td></tr>`;
    return;
  }
  dom.leadersBody.innerHTML = leaders.map((item) => `
    <tr>
      <td>${escapeHtml(item.code)} ${escapeHtml(item.name)}</td>
      <td>${escapeHtml(item.bucketName)}</td>
      <td class="${numberClass(item.activeReturn)}">${signedPct(item.activeReturn)}</td>
      <td class="${numberClass(item.activeRelativeReturn)}">${signedPct(item.activeRelativeReturn)}</td>
      <td>${ratioText(item.amountRatio)}</td>
      <td>${scoreText(item.outflowPressure)}</td>
      <td>${scoreText(item.absorptionScore)}</td>
      <td><span class="tag ${tagClass(item.status)}">${escapeHtml(item.status)}</span></td>
    </tr>
  `).join("");
}

function renderChart() {
  clearSvg(dom.chart);
  const payload = state.payload;
  const series = payload.series || {};
  const buckets = payload.buckets.filter((bucket) => series[bucket.key]?.length);
  if (!buckets.length) {
    dom.chartMeta.textContent = "-";
    dom.chart.appendChild(svgText("暂无相对强弱序列", 500, 160, "middle"));
    return;
  }
  const rows = buckets.flatMap((bucket) => series[bucket.key].map((row) => ({ ...row, bucket })));
  rows.forEach((row) => {
    row.dateMs = parseDate(row.date);
    row.relativeStrength = Number(row.relativeStrength);
  });
  const xMin = Math.min(...rows.map((row) => row.dateMs));
  const xMax = Math.max(...rows.map((row) => row.dateMs));
  let yMin = Math.min(...rows.map((row) => row.relativeStrength), 0);
  let yMax = Math.max(...rows.map((row) => row.relativeStrength), 0);
  const pad = Math.max((yMax - yMin) * 0.12, 0.01);
  yMin -= pad;
  yMax += pad;
  const box = BOX;
  const plot = box.plot;
  const width = box.width - plot.left - plot.right;
  const height = box.height - plot.top - plot.bottom;
  const xScale = (value) => plot.left + ((value - xMin) / Math.max(xMax - xMin, 1)) * width;
  const yScale = (value) => plot.top + (1 - (value - yMin) / Math.max(yMax - yMin, 1e-9)) * height;
  drawGrid(dom.chart, xMin, xMax, yMin, yMax, yScale);
  dom.chart.appendChild(svgEl("line", { x1: plot.left, x2: plot.left + width, y1: yScale(0), y2: yScale(0), class: "zero-line" }));
  buckets.forEach((bucket, index) => {
    const points = series[bucket.key].map((row) => ({
      dateMs: parseDate(row.date),
      value: Number(row.relativeStrength),
    }));
    dom.chart.appendChild(pathFor(points, xScale, yScale, { class: "series-line", stroke: bucket.color }));
    drawLegendItem(dom.chart, plot.left + index * 118, 10, bucket.color, bucket.name);
  });
  dom.chartMeta.textContent = `近 ${Math.max(...buckets.map((bucket) => series[bucket.key].length))} 个交易日，相对 ${payload.benchmark}`;
}

function drawGrid(svg, xMin, xMax, yMin, yMax, yScale) {
  const plot = BOX.plot;
  const width = BOX.width - plot.left - plot.right;
  const height = BOX.height - plot.top - plot.bottom;
  const group = svgEl("g", { class: "axis" });
  for (let i = 0; i <= 4; i++) {
    const value = yMax - (yMax - yMin) * i / 4;
    const y = yScale(value);
    group.appendChild(svgEl("line", { x1: plot.left, x2: plot.left + width, y1: y, y2: y, class: "grid-line" }));
    const text = svgEl("text", { x: plot.left - 8, y: y + 4, "text-anchor": "end" });
    text.textContent = pct(value);
    group.appendChild(text);
  }
  for (let i = 0; i <= 4; i++) {
    const x = plot.left + width * i / 4;
    const dateMs = xMin + (xMax - xMin) * i / 4;
    group.appendChild(svgEl("line", { x1: x, x2: x, y1: plot.top, y2: plot.top + height, class: "grid-line" }));
    const text = svgEl("text", { x, y: plot.top + height + 24, "text-anchor": "middle" });
    text.textContent = fmtDate(dateMs).slice(0, 7);
    group.appendChild(text);
  }
  svg.appendChild(group);
}

function pathFor(points, xScale, yScale, attrs) {
  const d = points.map((point, index) => `${index ? "L" : "M"}${xScale(point.dateMs).toFixed(1)},${yScale(point.value).toFixed(1)}`).join(" ");
  return svgEl("path", { d, ...attrs });
}

function drawLegendItem(svg, x, y, color, label) {
  svg.appendChild(svgEl("line", { x1: x, x2: x + 22, y1: y, y2: y, stroke: color, "stroke-width": 2.4 }));
  const text = svgEl("text", { x: x + 28, y: y + 4, class: "axis" });
  text.textContent = label;
  svg.appendChild(text);
}

function renderErrors() {
  const errors = state.payload?.errors || [];
  dom.errorsSection.hidden = !errors.length;
  dom.errors.innerHTML = errors.map((item) => `<div>${escapeHtml(item.code)} ${escapeHtml(item.name)}：${escapeHtml(item.error)}</div>`).join("");
}

function svgEl(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

function svgText(value, x, y, anchor) {
  const text = svgEl("text", { x, y, "text-anchor": anchor, class: "axis" });
  text.textContent = value;
  return text;
}

function clearSvg(svg) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
}

function parseDate(value) {
  return new Date(`${value}T00:00:00+08:00`).getTime();
}

function fmtDate(ms) {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function pct(value) {
  if (!Number.isFinite(Number(value))) return "-";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function signedPct(value) {
  if (!Number.isFinite(Number(value))) return "-";
  const number = Number(value);
  const sign = number > 0 ? "+" : "";
  return `${sign}${(number * 100).toFixed(2)}%`;
}

function ratioText(value) {
  if (!Number.isFinite(Number(value))) return "-";
  return `${Number(value).toFixed(2)}x`;
}

function scoreText(value) {
  if (!Number.isFinite(Number(value))) return "-";
  return Number(value).toFixed(1);
}

function numberClass(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "";
  return number > 0 ? "positive" : "negative";
}

function tagClass(status) {
  if (String(status).includes("承接")) return "good";
  if (String(status).includes("流出")) return "bad";
  if (String(status).includes("分歧")) return "warn";
  return "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

dom.refresh.addEventListener("click", () => loadRadar(true));
dom.buttons.forEach((button) => {
  button.addEventListener("click", () => {
    state.window = Number(button.dataset.window);
    loadRadar(false);
  });
});
loadRadar(false);
</script>
</body>
</html>"""
    return _inject_unified_shell(page).replace("__API_PATH__", "/api/capital-migration/radar.json")


def run_intraday_action(settings: Settings, write_alerts: bool = True) -> dict[str, object]:
    plan_path = latest_plan_path(settings.reports_dir)
    if plan_path is None:
        raise ValueError("No plan CSV found. Run plan first.")
    snapshot = read_realtime_snapshot(settings.qmt_realtime_path)
    monitor = build_intraday_monitor(load_plan(plan_path), snapshot)
    alerts = append_intraday_alerts(monitor, plan_path, settings.intraday_alert_log_path) if write_alerts else []
    status = write_intraday_status(monitor, plan_path, snapshot, settings.intraday_status_path, alerts)
    csv_path, md_path = write_intraday_reports(monitor, settings.reports_dir)
    return {
        "ok": True,
        "checked_at": status["checked_at"],
        "rows": status["rows"],
        "triggered": status["triggered"],
        "invalidated": status["invalidated"],
        "gap_skip": status["gap_skip"],
        "waiting": status["waiting"],
        "no_tick": status["no_tick"],
        "not_monitoring": status["not_monitoring"],
        "new_alerts": len(alerts),
        "plan": plan_path.name,
        "csv": csv_path.name,
        "markdown": md_path.name,
        "write_alerts": write_alerts,
        "message": f"完成：观察中 {status['waiting']}，新提醒 {len(alerts)}",
    }


def run_position_import_action(settings: Settings) -> dict[str, object]:
    terminal_error = ""
    if settings.qmt_sdk_path or settings.qmt_userdata_path:
        try:
            payload = import_terminal_positions(
                sdk_path=settings.qmt_sdk_path,
                userdata_path=settings.qmt_userdata_path,
                account_id=settings.qmt_account_id,
                snapshot_path=settings.qmt_position_snapshot_path,
                csv_path=settings.qmt_position_snapshot_csv_path,
            )
            return {
                "ok": True,
                "rows": payload["rows"],
                "source": payload["source_type"],
                "source_file": payload["source_file"],
                "snapshot": settings.qmt_position_snapshot_path.name,
                "csv": settings.qmt_position_snapshot_csv_path.name,
                "message": f"完成：从 QMT 导入持仓 {payload['rows']} 行",
            }
        except QmtUnavailable as exc:
            terminal_error = str(exc)
    if settings.qmt_position_export is None:
        hint = "；也可配置 QMT_POSITION_EXPORT 使用导出文件" if terminal_error else ""
        raise ValueError(f"QMT terminal positions unavailable: {terminal_error or 'not configured'}{hint}")
    payload = import_position_export(
        settings.qmt_position_export,
        settings.qmt_position_snapshot_path,
        settings.qmt_position_snapshot_csv_path,
    )
    return {
        "ok": True,
        "rows": payload["rows"],
        "source": payload["source_type"],
        "source_file": payload["source_file"],
        "snapshot": settings.qmt_position_snapshot_path.name,
        "csv": settings.qmt_position_snapshot_csv_path.name,
        "message": f"完成：从导出文件导入持仓 {payload['rows']} 行",
    }


def run_realtime_coverage_action(settings: Settings) -> dict[str, object]:
    position_snapshot = read_position_snapshot(settings.qmt_position_snapshot_path)
    plan_files = _latest_files(settings.reports_dir, ["plan_*.csv"], limit=1)
    plan_rows = _read_csv_preview(plan_files[0]) if plan_files else []
    symbols = _realtime_coverage_symbols(position_snapshot, plan_rows, settings.qmt_realtime_symbols)
    if not symbols:
        raise ValueError("No A-share symbols found in positions, latest plan, or QMT_REALTIME_SYMBOLS.")
    provider = QmtProvider(settings.qmt_sdk_path)
    payload = write_realtime_snapshot(settings.qmt_realtime_path, provider, symbols)
    ticks = payload.get("ticks", {})
    tick_count = len(ticks) if isinstance(ticks, dict) else 0
    return {
        "ok": True,
        "rows": len(symbols),
        "ticks": tick_count,
        "snapshot": settings.qmt_realtime_path.name,
        "symbols": symbols,
        "message": f"完成：刷新实时行情 {tick_count}/{len(symbols)} 个标的",
    }


def run_intraday_refresh_all_action(settings: Settings) -> dict[str, object]:
    positions = run_position_import_action(settings)
    realtime = run_realtime_coverage_action(settings)
    intraday = run_intraday_action(settings, write_alerts=True)
    position_rows = int(positions.get("rows") or 0)
    realtime_rows = int(realtime.get("rows") or 0)
    realtime_ticks = int(realtime.get("ticks") or 0)
    waiting = int(intraday.get("waiting") or 0)
    new_alerts = int(intraday.get("new_alerts") or 0)
    return {
        "ok": True,
        "positions": positions,
        "realtime": realtime,
        "intraday": intraday,
        "position_rows": position_rows,
        "realtime_rows": realtime_rows,
        "realtime_ticks": realtime_ticks,
        "waiting": waiting,
        "new_alerts": new_alerts,
        "message": (
            f"完成：持仓 {position_rows} 行，行情 {realtime_ticks}/{realtime_rows}，"
            f"观察中 {waiting}，新提醒 {new_alerts}"
        ),
    }


def _realtime_coverage_symbols(
    position_snapshot: dict[str, object] | None,
    plan_rows: list[dict[str, str]],
    configured_symbols: list[str],
) -> list[str]:
    symbols: list[str] = []

    def add(raw: object) -> None:
        symbol = str(raw or "").strip().upper()
        if _is_qmt_a_share_symbol(symbol) and symbol not in symbols:
            symbols.append(symbol)

    for symbol in configured_symbols:
        add(symbol)

    positions = (position_snapshot or {}).get("positions", [])
    for row in positions if isinstance(positions, list) else []:
        if isinstance(row, dict):
            add(row.get("symbol"))

    for row in plan_rows:
        action = str(row.get("action", "")).strip()
        if action in MONITORED_ACTIONS:
            add(row.get("symbol"))

    return sorted(symbols)


def _is_qmt_a_share_symbol(symbol: str) -> bool:
    return bool(A_SHARE_QMT_SYMBOL_RE.match(symbol))


def _status_card(title: str, ok: bool, detail: str | None = None) -> str:
    cls = "ok" if ok else "no"
    value = "可用" if ok else "未就绪"
    safe_detail = html.escape(detail or "")
    detail_html = f"<div class=\"label\">{safe_detail}</div>" if safe_detail else ""
    return f"<div class=\"metric\"><div class=\"label\">{html.escape(title)}</div><div class=\"value {cls}\">{value}</div>{detail_html}</div>"


def _channel_card_html(href: str, title: str, description: str) -> str:
    return (
        f"<a class=\"channel-card\" href=\"{html.escape(href)}\">"
        f"<span class=\"channel-title\">{html.escape(title)}</span>"
        f"<span class=\"channel-desc\">{html.escape(description)}</span>"
        "</a>"
    )


def _path_label(path: Path | None) -> str:
    return path.name if path else ""


def _qmt_status_detail(importable: bool, snapshot: dict[str, object] | None) -> str:
    if importable:
        return "当前进程可导入 xtquant"
    if snapshot:
        updated_at = str(snapshot.get("updated_at", ""))
        return f"读取本地快照 {updated_at}" if updated_at else "读取本地快照"
    return "未加载 xtquant，暂无本地快照"


def _qmt_position_detail(settings: Settings) -> str:
    userdata_path = resolve_qmt_userdata_path(settings.qmt_userdata_path, settings.qmt_sdk_path)
    account_id = resolve_qmt_account_id(settings.qmt_account_id, userdata_path) if userdata_path else None
    if userdata_path and account_id:
        return f"终端目录已识别，账号 {_mask_account(account_id)}"
    if settings.qmt_position_export:
        return f"导出文件 {_path_label(settings.qmt_position_export)}"
    if userdata_path:
        return "终端目录已识别，账号未识别"
    return "未配置"


def _qmt_snapshot_html(snapshot: dict[str, object] | None) -> str:
    if not snapshot:
        return "<div class=\"empty\">暂无 QMT 实时快照。使用 Python 3.11 运行 qmt-watch 后显示。</div>"
    ticks = snapshot.get("ticks")
    if not isinstance(ticks, dict) or not ticks:
        return "<div class=\"empty\">QMT 快照存在，但没有 tick 数据。</div>"
    columns = ["symbol", "lastPrice", "open", "high", "low", "time"]
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    rows = []
    for symbol, raw_tick in list(ticks.items())[:20]:
        tick = raw_tick if isinstance(raw_tick, dict) else {}
        values = {
            "symbol": symbol,
            "lastPrice": _format_tick_value(tick.get("lastPrice", tick.get("last_price", tick.get("price", "")))),
            "open": _format_tick_value(tick.get("open", "")),
            "high": _format_tick_value(tick.get("high", "")),
            "low": _format_tick_value(tick.get("low", "")),
            "time": str(tick.get("time", "")),
        }
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(values[column]))}</td>" for column in columns) + "</tr>")
    updated_at = html.escape(str(snapshot.get("updated_at", "")))
    table = f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    return f"<div class=\"note\">更新时间：{updated_at}</div>{table}"


def _position_snapshot_html(snapshot: dict[str, object] | None, settings: Settings) -> str:
    if not snapshot:
        if settings.qmt_sdk_path or settings.qmt_userdata_path:
            return "<div class=\"empty\">暂无真实持仓。启动独立交易端后，在 手动运行 里点 导入持仓。</div>"
        if settings.qmt_position_export is None:
            return "<div class=\"empty\">暂无真实持仓。先配置 QMT 终端或 QMT_POSITION_EXPORT，再点 导入持仓。</div>"
        return "<div class=\"empty\">暂无真实持仓。点 手动运行 里的 导入持仓。</div>"
    positions = snapshot.get("positions")
    if not isinstance(positions, list) or not positions:
        imported_at = html.escape(str(snapshot.get("imported_at", "")))
        return f"<div class=\"empty\">持仓快照为空。更新时间：{imported_at}</div>"
    columns = [
        "symbol",
        "name",
        "quantity",
        "available_quantity",
        "last_price",
        "market_value",
        "cost_price",
        "profit_loss",
        "profit_loss_pct",
        "position_pct",
    ]
    imported_at = html.escape(str(snapshot.get("imported_at", "")))
    source_file = html.escape(str(snapshot.get("source_file", "")))
    source_type = html.escape(str(snapshot.get("source_type", "")))
    account = html.escape(str(snapshot.get("account_id", "")))
    account_text = f" 账号：{account}" if account else ""
    note = f"<div class=\"note\">更新时间：{imported_at} 来源：{source_file} {source_type}{account_text}</div>"
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    rows = []
    for raw in positions[:20]:
        row = raw if isinstance(raw, dict) else {}
        cells = [
            f"<td>{html.escape(_format_position_cell(column, row.get(column, '')))}</td>"
            for column in columns
        ]
        rows.append("<tr>" + "".join(cells) + "</tr>")
    table = f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    return note + table


def _today_work_rows(
    position_snapshot: dict[str, object] | None,
    plan_rows: list[dict[str, str]],
    intraday_rows: list[dict[str, str]],
    qmt_snapshot: dict[str, object] | None,
) -> list[dict[str, object]]:
    positions = {
        str(row.get("symbol", "")).strip().upper(): row
        for row in (position_snapshot or {}).get("positions", [])
        if isinstance(row, dict) and str(row.get("symbol", "")).strip()
    }
    plan_by_symbol = {
        str(row.get("symbol", "")).strip().upper(): row
        for row in plan_rows
        if str(row.get("symbol", "")).strip()
    }
    active_plan_symbols = {
        symbol
        for symbol, row in plan_by_symbol.items()
        if str(row.get("action", "")).strip() in MONITORED_ACTIONS
    }
    monitor_by_symbol = {
        str(row.get("symbol", "")).strip().upper(): row
        for row in intraday_rows
        if str(row.get("symbol", "")).strip()
    }
    ticks = qmt_snapshot.get("ticks", {}) if qmt_snapshot else {}
    ticks = ticks if isinstance(ticks, dict) else {}

    rows: list[dict[str, object]] = []
    for symbol in sorted(set(positions) | active_plan_symbols):
        position = positions.get(symbol, {})
        plan = plan_by_symbol.get(symbol, {})
        monitor = monitor_by_symbol.get(symbol, {})
        tick = ticks.get(symbol, {}) if isinstance(ticks.get(symbol, {}), dict) else {}
        has_position = symbol in positions and (
            (_float_value(position.get("quantity")) or 0) > 0
            or (_float_value(position.get("market_value")) or 0) > 0
        )
        plan_action = str(plan.get("action", "")).strip()
        status = str(monitor.get("intraday_status") or "").strip()
        if not status:
            if plan_action in MONITORED_ACTIONS and not tick:
                status = "no_tick"
            elif plan:
                status = "not_monitoring"
            else:
                status = "not_in_plan"

        has_plan = bool(plan)
        last_price = monitor.get("last_price") or tick.get("lastPrice") or position.get("last_price")
        has_realtime_price = bool(monitor.get("last_price") or tick.get("lastPrice"))
        level, reason, rank, level_class = _today_work_decision(
            has_position=has_position,
            has_plan=has_plan,
            plan_action=plan_action,
            status=status,
            block_reasons=str(plan.get("block_reasons", "")).strip(),
        )
        research_priority_score, research_priority = (
            _research_priority(
                has_plan=has_plan,
                has_realtime_price=has_realtime_price,
                position_pct=position.get("position_pct"),
                profit_loss_pct=position.get("profit_loss_pct"),
                status=status,
            )
            if level_class == "work-review"
            else (0, "")
        )
        name = str(position.get("name") or plan.get("name") or "").strip()
        row = {
            "rank": rank,
            "level_class": level_class,
            "level": level,
            "symbol": symbol,
            "name": name,
            "kind": _today_work_kind(has_position, has_plan, plan_action),
            "status": status,
            "last_price": last_price,
            "position_pct": position.get("position_pct"),
            "profit_loss_pct": position.get("profit_loss_pct"),
            "research_priority": research_priority,
            "research_priority_score": research_priority_score,
            "trigger_price": monitor.get("trigger_price") or plan.get("trigger_price"),
            "invalid_price": monitor.get("invalid_price") or plan.get("invalid_price"),
            "distance_to_trigger_pct": monitor.get("distance_to_trigger_pct"),
            "reason": reason,
            "score": _float_value(plan.get("score")) or 0,
        }
        rows.append(row)

    return sorted(rows, key=lambda row: (int(row["rank"]), -float(row["score"]), str(row["symbol"])))


def _today_work_decision(
    *,
    has_position: bool,
    has_plan: bool,
    plan_action: str,
    status: str,
    block_reasons: str,
) -> tuple[str, str, int, str]:
    if has_position and not has_plan:
        return "补研究", "已持仓但不在最新计划里，先补研究和风控条件", 20, "work-review"
    if has_position and status == "invalidated":
        return "人工检查", "已持仓且实时价到达或跌破失效价", 0, "work-urgent"
    if has_position and status == "triggered":
        return "重点盯盘", "已持仓且达到计划触发价，检查是否继续持有", 5, "work-focus"
    if has_position and status == "gap_skip":
        return "不追高", "已持仓但开盘超过计划上限，不做追涨处理", 8, "work-focus"
    if has_position and status == "no_tick":
        return "补行情", "已持仓但没有实时价，先补 QMT 行情覆盖", 12, "work-review"
    if has_position and status == "not_monitoring":
        reason = f"已持仓但计划暂不监控：{block_reasons}" if block_reasons else "已持仓但计划暂不监控"
        return "补研究", reason, 18, "work-review"
    if has_position:
        return "持仓观察", "已持仓，当前未触发也未失效", 25, "work-muted"
    if status == "triggered":
        return "人工复核", "观察票已达到触发价，人工复核后再决定", 30, "work-focus"
    if status == "gap_skip":
        return "跳过", "开盘超过计划上限，不追", 40, "work-muted"
    if status == "invalidated":
        return "失效", "观察票已跌破失效价", 45, "work-muted"
    if status == "no_tick":
        return "无行情", "观察票没有实时价，无法判断", 50, "work-review"
    if plan_action in MONITORED_ACTIONS:
        return "等待", "观察票尚未触发", 60, "work-muted"
    return "暂不处理", "不在今日监控范围", 90, "work-muted"


def _today_work_kind(has_position: bool, has_plan: bool, plan_action: str) -> str:
    if has_position and has_plan:
        return "持仓+计划"
    if has_position:
        return "持仓"
    if plan_action in MONITORED_ACTIONS:
        return "观察"
    return "计划"


def _research_priority(
    *,
    has_plan: bool,
    has_realtime_price: bool,
    position_pct: object,
    profit_loss_pct: object,
    status: str,
) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []
    position_ratio = _ratio_value(position_pct)
    profit_ratio = _ratio_value(profit_loss_pct)

    if position_ratio is not None:
        if position_ratio >= 0.08:
            score += 40
            reasons.append(f"仓位{position_ratio:.2%}")
        elif position_ratio >= 0.03:
            score += 25
            reasons.append(f"仓位{position_ratio:.2%}")
        elif position_ratio > 0:
            score += 10

    if profit_ratio is not None:
        if profit_ratio <= -0.10:
            score += 35
            reasons.append(f"浮亏{abs(profit_ratio):.2%}")
        elif profit_ratio <= -0.05:
            score += 25
            reasons.append(f"浮亏{abs(profit_ratio):.2%}")
        elif profit_ratio < 0:
            score += 10
            reasons.append(f"浮亏{abs(profit_ratio):.2%}")
    else:
        score += 5
        reasons.append("无盈亏率")

    if not has_plan:
        score += 20
        reasons.append("未进计划")
    if not has_realtime_price:
        score += 15
        reasons.append("无实时价")
    if status == "not_monitoring":
        score += 10
        reasons.append("计划暂不监控")

    if score >= 60:
        label = "高"
    elif score >= 30:
        label = "中"
    else:
        label = "低"
    detail = "；".join(reasons) if reasons else "待补研究"
    return score, f"{label}：{detail}"


def _today_work_html(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<div class=\"empty\">暂无今日处理清单。需要先导入真实持仓，并生成明日计划或 QMT 实时快照。</div>"
    columns = [
        ("level", "级别"),
        ("research_priority", "优先级"),
        ("symbol", "代码"),
        ("name", "名称"),
        ("kind", "类型"),
        ("status", "状态"),
        ("last_price", "现价"),
        ("position_pct", "仓位"),
        ("profit_loss_pct", "盈亏率"),
        ("trigger_price", "触发价"),
        ("invalid_price", "失效价"),
        ("distance_to_trigger_pct", "距触发"),
        ("reason", "处理原因"),
    ]
    groups = _today_work_group_rows(rows)
    has_actionable = bool(groups["must"] or groups["research"])
    summary = (
        "<div class=\"work-overview\">"
        f"<span><strong>{len(groups['must'])}</strong> 必须检查</span>"
        f"<span><strong>{len(groups['research'])}</strong> 补研究</span>"
        f"<span><strong>{len(groups['observe'])}</strong> 继续观察</span>"
        "</div>"
    )
    note = "<div class=\"note\">按风险和可处理程度分组。这里只做人工处理提示，不生成下单动作。</div>"
    sections = []
    for key, title in [
        ("must", "必须检查"),
        ("research", "补研究"),
        ("observe", "继续观察"),
    ]:
        group_rows = groups[key]
        open_attr = " open" if key != "observe" or not has_actionable else ""
        body = _today_work_table_html(group_rows, columns) if group_rows else "<div class=\"empty\">暂无</div>"
        sections.append(
            f"<details class=\"work-group\"{open_attr}>"
            f"<summary><span class=\"work-group-title\">{title}</span>"
            f"<span class=\"work-group-meta\">{len(group_rows)} 项</span></summary>"
            f"{body}</details>"
        )
    return "<div class=\"work-board\">" + note + summary + "".join(sections) + "</div>"


def _today_work_group_rows(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = {"must": [], "research": [], "observe": []}
    for row in rows:
        groups[_today_work_group_key(row)].append(row)
    groups["research"].sort(key=_today_work_research_sort_key)
    return groups


def _today_work_research_sort_key(row: dict[str, object]) -> tuple[int, float, float, str]:
    priority = int(row.get("research_priority_score") or 0)
    position_ratio = _ratio_value(row.get("position_pct")) or 0
    profit_ratio = _ratio_value(row.get("profit_loss_pct"))
    return (-priority, -position_ratio, profit_ratio if profit_ratio is not None else 1, str(row.get("symbol", "")))


def _today_work_group_key(row: dict[str, object]) -> str:
    level_class = str(row.get("level_class", ""))
    level = str(row.get("level", ""))
    if level_class in {"work-urgent", "work-focus"}:
        return "must"
    if level_class == "work-review" or level in {"补研究", "补行情", "无行情"}:
        return "research"
    return "observe"


def _today_work_table_html(rows: list[dict[str, object]], columns: list[tuple[str, str]]) -> str:
    header = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    body = []
    for row in rows:
        cells = []
        for key, _label in columns:
            text = _format_today_work_cell(key, row.get(key, ""))
            cls = str(row.get("level_class", "")) if key == "level" else f"status-{row.get(key, '')}" if key == "status" else ""
            cells.append(f"<td class=\"{html.escape(cls)}\">{html.escape(text)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _format_today_work_cell(column: str, value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    if column == "status":
        return {
            "triggered": "已触发",
            "invalidated": "已失效",
            "gap_skip": "高开跳过",
            "waiting": "等待",
            "no_tick": "无实时价",
            "not_monitoring": "暂不监控",
            "not_in_plan": "不在计划",
        }.get(text, text)
    if column in {"last_price", "trigger_price", "invalid_price"}:
        try:
            return f"{float(text):.3f}"
        except ValueError:
            return text
    if column in {"position_pct", "profit_loss_pct", "distance_to_trigger_pct"}:
        value_float = _ratio_value(value)
        return f"{value_float:.2%}" if value_float is not None else text
    return text.replace(" 00:00:00", "")


def _intraday_rows(settings: Settings, snapshot: dict[str, object] | None) -> list[dict[str, str]]:
    plan_path = latest_plan_path(settings.reports_dir)
    if plan_path is None:
        return []
    monitor = build_intraday_monitor(load_plan(plan_path), snapshot)
    if monitor.empty:
        return []
    return [{str(key): "" if pd.isna(value) else str(value) for key, value in row.items()} for row in monitor.to_dict("records")]


def _action_controls_html() -> str:
    return (
        "<div class=\"actions\">"
        "<button type=\"button\" data-action-path=\"/actions/intraday-refresh-all\">一键盘中刷新</button>"
        "<button type=\"button\" data-action-path=\"/actions/intraday-monitor\">Run 监控</button>"
        "<button type=\"button\" class=\"secondary\" data-action-path=\"/actions/intraday-monitor-no-alerts\">Run 不写提醒</button>"
        "<button type=\"button\" class=\"secondary\" data-action-path=\"/actions/qmt-positions\">导入持仓</button>"
        "<button type=\"button\" class=\"secondary\" data-action-path=\"/actions/qmt-realtime-coverage\">刷新全量行情</button>"
        "</div>"
        "<div id=\"action-output\" class=\"action-result\" aria-live=\"polite\"></div>"
    )


def _watch_status_html(status: dict[str, object] | None) -> str:
    if not status:
        return "<div class=\"empty\">自动监控未启动。运行 intraday-watch 后显示最近检查结果。</div>"
    items = [
        ("最近检查", str(status.get("checked_at", ""))),
        ("计划文件", str(status.get("plan_file", ""))),
        ("观察中", str(status.get("waiting", 0))),
        ("新提醒", str(status.get("new_alerts", 0))),
        ("触发", str(status.get("triggered", 0))),
        ("失效", str(status.get("invalidated", 0))),
        ("高开跳过", str(status.get("gap_skip", 0))),
        ("无 tick", str(status.get("no_tick", 0))),
    ]
    cards = [
        f"<div class=\"metric\"><div class=\"label\">{html.escape(label)}</div><div class=\"value\">{html.escape(value)}</div></div>"
        for label, value in items
    ]
    return "<div class=\"status-grid\">" + "".join(cards) + "</div>"


def _intraday_table_html(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<div class=\"empty\">暂无盘中监控。需要先生成 plan，并运行 QMT 实时刷新。</div>"
    columns = [
        "symbol",
        "name",
        "plan_action",
        "intraday_status",
        "last_price",
        "trigger_price",
        "invalid_price",
        "max_open_price",
        "distance_to_trigger_pct",
        "qmt_time",
        "note",
    ]
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in rows[:20]:
        cells = []
        for column in columns:
            value = _format_intraday_cell(column, row.get(column, ""))
            cls = f"status-{row.get(column, '')}" if column == "intraday_status" else ""
            cells.append(f"<td class=\"{cls}\">{html.escape(value)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _alert_table_html(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<div class=\"empty\">暂无盘中提醒。只有 triggered、invalidated、gap_skip 会写入提醒。</div>"
    columns = [
        "observed_at",
        "symbol",
        "name",
        "status",
        "last_price",
        "trigger_price",
        "invalid_price",
        "qmt_time",
        "message",
    ]
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in rows[:20]:
        cells = []
        for column in columns:
            value = _format_alert_cell(column, row.get(column, ""))
            cls = f"status-{row.get(column, '')}" if column == "status" else ""
            cells.append(f"<td class=\"{cls}\">{html.escape(value)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _format_alert_cell(column: str, value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if column in {"last_price", "trigger_price", "invalid_price"}:
        try:
            return f"{float(text):.3f}"
        except ValueError:
            return text
    return text.replace(" 00:00:00", "")


def _format_position_cell(column: str, value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    if column in {"quantity", "available_quantity"}:
        try:
            return f"{float(text):.0f}"
        except ValueError:
            return text
    if column in {"last_price", "market_value", "cost_price", "profit_loss"}:
        try:
            return f"{float(text):.3f}"
        except ValueError:
            return text
    if column in {"profit_loss_pct", "position_pct"}:
        try:
            value_float = float(text)
        except ValueError:
            return text
        if abs(value_float) > 1:
            return f"{value_float:.2f}%"
        return f"{value_float:.2%}"
    return text.replace(" 00:00:00", "")


def _mask_account(account_id: str) -> str:
    if len(account_id) <= 4:
        return "*" * len(account_id)
    return "*" * (len(account_id) - 4) + account_id[-4:]


def _format_intraday_cell(column: str, value: str) -> str:
    if value is None:
        return ""
    text = str(value)
    if column in {"distance_to_trigger_pct", "distance_to_invalid_pct"}:
        try:
            return f"{float(text):.2%}"
        except ValueError:
            return text
    if column in {"last_price", "trigger_price", "invalid_price", "max_open_price"}:
        try:
            return f"{float(text):.3f}"
        except ValueError:
            return text
    return text.replace(" 00:00:00", "")


def _format_tick_value(value: object) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "" if value is None else str(value)


def _float_value(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(str(value).strip().replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _ratio_value(value: object) -> float | None:
    value_float = _float_value(value)
    if value_float is None:
        return None
    if abs(value_float) > 1:
        return value_float / 100
    return value_float


def _metrics_html(metrics: dict[str, str]) -> str:
    if not metrics:
        return "<div class=\"empty\">暂无回测输出</div>"
    items = [
        ("末值权益", metrics.get("equity", "")),
        ("策略收益", metrics.get("strategy_return", "")),
        ("持仓状态", metrics.get("position", "")),
        ("日期", metrics.get("date", "")),
    ]
    cards = [
        f"<div class=\"metric\"><div class=\"label\">{html.escape(label)}</div><div class=\"value\">{html.escape(value)}</div></div>"
        for label, value in items
    ]
    return "<div class=\"status-grid\">" + "".join(cards) + "</div>"


def _scan_table_html(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<div class=\"empty\">暂无扫描输出</div>"
    columns = ["symbol", "name", "date", "close", "score", "signal", "setup", "stop_loss_pct", "position_weight_cap", "source"]
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in rows[:20]:
        cells = []
        for column in columns:
            value = row.get(column, "")
            cls = ""
            if column == "signal":
                cls = "signal-true" if value.lower() == "true" else "signal-false"
            cells.append(f"<td class=\"{cls}\">{html.escape(value)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _plan_table_html(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<div class=\"empty\">暂无明日计划。运行 python -m shortterm_trader.cli plan 后显示。</div>"
    columns = [
        "symbol",
        "name",
        "date",
        "action",
        "score",
        "setup",
        "close",
        "trigger_price",
        "invalid_price",
        "stop_loss_pct",
        "position_weight_cap",
        "block_reasons",
    ]
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in rows[:20]:
        cells = []
        for column in columns:
            value = _format_plan_cell(column, row.get(column, ""))
            cls = ""
            if column == "action":
                raw_action = row.get(column, "")
                if raw_action == "candidate":
                    cls = "action-candidate"
                elif raw_action == "watch_if_trigger":
                    cls = "action-watch"
                else:
                    cls = "action-blocked"
            cells.append(f"<td class=\"{cls}\">{html.escape(value)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _format_plan_cell(column: str, value: str) -> str:
    if value is None:
        return ""
    text = str(value)
    if column in {"stop_loss_pct", "position_weight_cap"}:
        try:
            return f"{float(text):.2%}"
        except ValueError:
            return text
    if column in {"close", "trigger_price", "invalid_price"}:
        try:
            return f"{float(text):.3f}"
        except ValueError:
            return text
    if column == "date":
        return text.replace(" 00:00:00", "")
    return text


def _coverage_table_html(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<div class=\"empty\">暂无入库行情。运行 sync-bars、scan、plan 或 backtest 后自动写入。</div>"
    columns = ["symbol", "rows", "start_date", "end_date", "sources", "updated_at"]
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in rows:
        cells = [f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns]
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _file_list_html(files: list[Path], kind: str) -> str:
    if not files:
        return "<div class=\"empty\">暂无文件</div>"
    rows = []
    for path in files:
        modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size = _format_size(path.stat().st_size)
        if kind == "reports":
            link = f"<a href=\"/reports/{quote(path.name)}\">{html.escape(path.name)}</a>"
        else:
            link = html.escape(path.name)
        rows.append(f"<tr><td>{link}</td><td>{size}</td><td>{modified}</td></tr>")
    return "<table><thead><tr><th>文件</th><th>大小</th><th>时间</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _latest_files(base: Path, patterns: list[str], limit: int) -> list[Path]:
    if not base.exists():
        return []
    files: list[Path] = []
    for pattern in patterns:
        files.extend(path for path in base.glob(pattern) if path.is_file())
    unique = sorted(set(files), key=lambda path: path.stat().st_mtime, reverse=True)
    return unique[:limit]


def _read_csv_preview(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _backtest_snapshot(path: Path) -> dict[str, str]:
    rows = _read_csv_preview(path)
    if not rows:
        return {}
    row = rows[-1]
    return {
        "date": row.get("date", ""),
        "equity": _fmt_float(row.get("equity"), suffix="x"),
        "strategy_return": _fmt_pct(row.get("strategy_return")),
        "position": _fmt_pct(row.get("position")),
    }


def _fmt_pct(value: str | None) -> str:
    try:
        return f"{float(value or 0):.2%}"
    except ValueError:
        return ""


def _fmt_float(value: str | None, suffix: str = "") -> str:
    try:
        return f"{float(value or 0):.3f}{suffix}"
    except ValueError:
        return ""


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def run(host: str = "127.0.0.1", port: int = 8009) -> None:
    settings = load_settings()
    DashboardHandler.settings = settings
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(json.dumps({"url": f"http://{host}:{port}", "settings": asdict(settings)}, ensure_ascii=False, default=str))
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local MyShortTerm dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8009)
    args = parser.parse_args(argv)
    run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
