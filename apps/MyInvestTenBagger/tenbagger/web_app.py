"""FastAPI web display for local TASK 1 results."""

from __future__ import annotations

import html
import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from tenbagger.config import DEFAULT_REPORT_DIR
from tenbagger.revaluation import run_universe_revaluation
from tenbagger.universe import UniverseManager


SYSTEM_NAME = "TenBagger"
SYSTEM_VERSION = "0.2.0"
SYSTEM_DESCRIPTION = (
    "Local A-share tenbagger research system with Model V2 scoring, "
    "market regime, behavior, structure, and anomaly dashboards."
)


def create_app(report_dir: Path | str = DEFAULT_REPORT_DIR) -> FastAPI:
    app = FastAPI(title="TenBagger")
    report_path = Path(report_dir) / "task1_summary.json"
    factor_report_path = Path(report_dir) / "task2_factor_summary.json"
    screener_report_path = Path(report_dir) / "task3_screener_summary.json"
    backtest_report_path = Path(report_dir) / "task4_backtest_summary.json"
    optimization_report_path = Path(report_dir) / "task5_optimization_summary.json"
    monetization_report_path = Path(report_dir) / "task6_monetization_summary.json"
    structural_report_path = Path(report_dir) / "task7_structural_validation_summary.json"
    regime_report_path = Path(report_dir) / "task8_regime_summary.json"
    behavior_report_path = Path(report_dir) / "task9_behavior_summary.json"
    structure_report_path = Path(report_dir) / "task10_structure_summary.json"
    anomaly_report_path = Path(report_dir) / "task11_anomaly_summary.json"

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api")
    def api_catalog(request: Request) -> JSONResponse:
        base_url = str(request.base_url).rstrip("/")
        return JSONResponse(_build_api_catalog(base_url=base_url))

    @app.get("/api/task1")
    def task1_api() -> JSONResponse:
        report = _load_report(report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 1 report not found"}, status_code=status)

    @app.get("/api/universe")
    def universe_api(level: str = "dev") -> JSONResponse:
        try:
            details = UniverseManager.get_details(level)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(details)

    @app.get("/api/universe/revaluation")
    def universe_revaluation_api(baseline: str = "dev", target: str = "research") -> JSONResponse:
        try:
            result = run_universe_revaluation(
                report_root=Path(report_dir),
                output_dir=Path(report_dir),
                baseline_level=baseline,
                target_level=target,
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(result)

    @app.get("/api/task2")
    def task2_api() -> JSONResponse:
        report = _load_report(factor_report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 2 report not found"}, status_code=status)

    @app.get("/api/task3")
    def task3_api() -> JSONResponse:
        report = _load_report(screener_report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 3 report not found"}, status_code=status)

    @app.get("/api/task4")
    def task4_api() -> JSONResponse:
        report = _load_report(backtest_report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 4 report not found"}, status_code=status)

    @app.get("/api/task5")
    def task5_api() -> JSONResponse:
        report = _load_report(optimization_report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 5 report not found"}, status_code=status)

    @app.get("/api/task6")
    def task6_api() -> JSONResponse:
        report = _load_report(monetization_report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 6 report not found"}, status_code=status)

    @app.get("/api/task7")
    def task7_api() -> JSONResponse:
        report = _load_report(structural_report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 7 report not found"}, status_code=status)

    @app.get("/api/task8")
    def task8_api() -> JSONResponse:
        report = _load_report(regime_report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 8 report not found"}, status_code=status)

    @app.get("/api/task8/regime")
    def task8_regime_api() -> JSONResponse:
        report = _load_report(regime_report_path)
        status = 200 if report else 404
        return JSONResponse(report.get("api_response", {}) if report else {"error": "TASK 8 report not found"}, status_code=status)

    @app.get("/api/task9")
    def task9_api() -> JSONResponse:
        report = _load_report(behavior_report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 9 report not found"}, status_code=status)

    @app.get("/api/task9/behavior")
    def task9_behavior_api() -> JSONResponse:
        report = _load_report(behavior_report_path)
        status = 200 if report else 404
        return JSONResponse(report.get("api_response", {}) if report else {"error": "TASK 9 report not found"}, status_code=status)

    @app.get("/api/task10")
    def task10_api() -> JSONResponse:
        report = _load_report(structure_report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 10 report not found"}, status_code=status)

    @app.get("/api/task10/structure")
    def task10_structure_api() -> JSONResponse:
        report = _load_report(structure_report_path)
        status = 200 if report else 404
        return JSONResponse(report.get("api_response", {}) if report else {"error": "TASK 10 report not found"}, status_code=status)

    @app.get("/api/task11")
    def task11_api() -> JSONResponse:
        report = _load_report(anomaly_report_path)
        status = 200 if report else 404
        return JSONResponse(report or {"error": "TASK 11 report not found"}, status_code=status)

    @app.get("/api/task11/anomaly")
    def task11_anomaly_api() -> JSONResponse:
        report = _load_report(anomaly_report_path)
        status = 200 if report else 404
        return JSONResponse(report.get("api_response", {}) if report else {"error": "TASK 11 report not found"}, status_code=status)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _dashboard_response("v2")

    @app.get("/model/v1", response_class=HTMLResponse)
    def model_v1() -> str:
        return _dashboard_response("v1")

    def _dashboard_response(model_version: str) -> str:
        report = _load_report(report_path)
        factor_report = _load_report(factor_report_path)
        screener_report = _load_report(screener_report_path)
        backtest_report = _load_report(backtest_report_path)
        optimization_report = _load_report(optimization_report_path)
        monetization_report = _load_report(monetization_report_path)
        structural_report = _load_report(structural_report_path)
        regime_report = _load_report(regime_report_path)
        behavior_report = _load_report(behavior_report_path)
        structure_report = _load_report(structure_report_path)
        anomaly_report = _load_report(anomaly_report_path)
        return _render_dashboard(
            report,
            factor_report,
            screener_report,
            backtest_report,
            optimization_report,
            monetization_report,
            structural_report,
            regime_report,
            behavior_report,
            structure_report,
            anomaly_report,
            model_version=model_version,
        )

    return app


app = create_app()


def _load_report(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _endpoint(
    method: str,
    path: str,
    purpose: str,
    parameters: list[dict[str, Any]] | None,
    returns: str,
    read_only: bool = True,
) -> dict[str, Any]:
    return {
        "method": method,
        "path": path,
        "purpose": purpose,
        "parameters": parameters or [],
        "returns": returns,
        "read_only": read_only,
    }


def _build_api_catalog(base_url: str = "") -> dict[str, Any]:
    docs = {
        "swagger_ui": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
    }
    groups = [
        {
            "name": "文档入口",
            "description": "Human-readable pages and generated API documentation.",
            "endpoints": [
                _endpoint("GET", "/api", "Unified API catalog for this system.", [], "JSON endpoint catalog and safety notes."),
                _endpoint("GET", "/", "Default Model V2 web dashboard.", [], "HTML dashboard."),
                _endpoint("GET", "/model/v1", "Legacy Model V1 web dashboard for comparison.", [], "HTML dashboard."),
                _endpoint("GET", "/docs", "FastAPI Swagger UI.", [], "Interactive API documentation page."),
                _endpoint("GET", "/redoc", "FastAPI ReDoc UI.", [], "Alternative API documentation page."),
                _endpoint("GET", "/openapi.json", "OpenAPI schema.", [], "OpenAPI JSON schema."),
            ],
        },
        {
            "name": "系统状态",
            "description": "Service health and local runtime status.",
            "endpoints": [
                _endpoint("GET", "/health", "Health check for the local web service.", [], "JSON status object."),
            ],
        },
        {
            "name": "当前数据",
            "description": "Current local universe, data coverage, latest snapshots, and factor outputs.",
            "endpoints": [
                _endpoint(
                    "GET",
                    "/api/universe",
                    "Resolve the stock universe for a level.",
                    [
                        {
                            "name": "level",
                            "in": "query",
                            "required": False,
                            "default": "dev",
                            "description": "Universe level: dev, research, or production.",
                        }
                    ],
                    "Universe metadata, selected stock codes, source, and filter stats.",
                ),
                _endpoint("GET", "/api/task1", "TASK 1 data layer summary.", [], "Stock count, missing rates, coverage, and latest snapshot."),
                _endpoint("GET", "/api/task2", "TASK 2 factor engine summary.", [], "Factor validation, latest V1/V2 scores, and Model V2 summary."),
                _endpoint("GET", "/api/task3", "TASK 3 screener and alpha validation summary.", [], "V1 candidates, V2 candidates, IC curves, and preview backtests."),
            ],
        },
        {
            "name": "历史数据",
            "description": "Backtest, optimization, monetization, and structural alpha reports from existing local outputs.",
            "endpoints": [
                _endpoint("GET", "/api/task4", "TASK 4 legacy portfolio simulation report.", [], "Portfolio NAV metrics, benchmarks, holdings, and factor attribution."),
                _endpoint("GET", "/api/task5", "TASK 5 legacy factor optimization report.", [], "Best weights, baseline/optimized metrics, and IC comparison."),
                _endpoint("GET", "/api/task6", "TASK 6 legacy alpha monetization report.", [], "Best config, test metrics, cost sensitivity, and decay diagnostics."),
                _endpoint("GET", "/api/task7", "TASK 7 legacy structural alpha validation report.", [], "OOS metrics, stability, randomization, and alpha classification."),
            ],
        },
        {
            "name": "分析结果",
            "description": "Market regime, behavior, structure, anomaly, and universe comparison results.",
            "endpoints": [
                _endpoint("GET", "/api/task8", "TASK 8 full market regime report.", [], "Regime latest state, validation, history, and source metadata."),
                _endpoint("GET", "/api/task8/regime", "TASK 8 compact current regime response.", [], "Current trend, volatility, liquidity, and behavior state."),
                _endpoint("GET", "/api/task9", "TASK 9 full market behavior and flow report.", [], "Behavior latest state, validation, history, and source metadata."),
                _endpoint("GET", "/api/task9/behavior", "TASK 9 compact behavior response.", [], "Current flow actor, panic/FOMO, crowding, and divergence metrics."),
                _endpoint("GET", "/api/task10", "TASK 10 full market structure decomposition report.", [], "Structure latest state, validation, history, and source metadata."),
                _endpoint("GET", "/api/task10/structure", "TASK 10 compact structure response.", [], "Current return decomposition, dispersion, correlation, and shock metrics."),
                _endpoint("GET", "/api/task11", "TASK 11 full structural anomaly report.", [], "Anomaly latest state, validation, history, and source metadata."),
                _endpoint("GET", "/api/task11/anomaly", "TASK 11 compact anomaly response.", [], "Current anomaly score, systemic risk, and dominant anomaly type."),
                _endpoint(
                    "GET",
                    "/api/universe/revaluation",
                    "Compare generated reports between two universe levels.",
                    [
                        {
                            "name": "baseline",
                            "in": "query",
                            "required": False,
                            "default": "dev",
                            "description": "Baseline universe level.",
                        },
                        {
                            "name": "target",
                            "in": "query",
                            "required": False,
                            "default": "research",
                            "description": "Target universe level.",
                        },
                    ],
                    "Universe comparison summary; this endpoint may write a revaluation report.",
                    read_only=False,
                ),
            ],
        },
    ]
    endpoint_count = sum(len(group["endpoints"]) for group in groups)
    return {
        "system_name": SYSTEM_NAME,
        "version": SYSTEM_VERSION,
        "description": SYSTEM_DESCRIPTION,
        "base_url": base_url,
        "docs": docs,
        "recommended_entrypoints": [
            {"path": "/api", "reason": "Start here for endpoint discovery and safety notes."},
            {"path": "/", "reason": "Default Model V2 web dashboard."},
            {"path": "/api/task3", "reason": "Model V2 candidates and IC preview."},
            {"path": "/api/task8/regime", "reason": "Current market regime snapshot."},
            {"path": "/api/task9/behavior", "reason": "Current behavior and flow snapshot."},
            {"path": "/api/task10/structure", "reason": "Current market structure snapshot."},
            {"path": "/api/task11/anomaly", "reason": "Current structural anomaly snapshot."},
        ],
        "safety": {
            "catalog_read_only": True,
            "default_boundary": "GET /api 只描述接口，不触发重计算、写入、交易、同步或外部下单。",
            "trading_boundary": "当前系统没有交易、券商写入或下单 API；Web/API 默认只用于本地研究展示，除非某个接口明确标记为非只读。",
            "non_read_only_endpoints": [
                {
                    "method": "GET",
                    "path": "/api/universe/revaluation",
                    "reason": "Runs a comparison over existing reports and may write local revaluation output files.",
                }
            ],
        },
        "groups": groups,
        "total_endpoints": endpoint_count,
    }


def _render_dashboard(
    report: dict[str, Any] | None,
    factor_report: dict[str, Any] | None,
    screener_report: dict[str, Any] | None,
    backtest_report: dict[str, Any] | None,
    optimization_report: dict[str, Any] | None,
    monetization_report: dict[str, Any] | None,
    structural_report: dict[str, Any] | None,
    regime_report: dict[str, Any] | None,
    behavior_report: dict[str, Any] | None,
    structure_report: dict[str, Any] | None,
    anomaly_report: dict[str, Any] | None,
    model_version: str = "v2",
) -> str:
    if report is None:
        api_catalog_section = _render_api_catalog_section(_build_api_catalog())
        content = """
        <main class="shell">
          <section class="empty">
            <h1>TenBagger</h1>
            <p>TASK 1 report not found. Run the data loader first.</p>
          </section>
          {api_catalog_section}
        </main>
        """.format(api_catalog_section=api_catalog_section)
        return _page(content)

    missing = report.get("missing_rates", {})
    coverage = report.get("stock_coverage", [])
    snapshot = report.get("latest_snapshot", [])
    stock_names = _stock_name_lookup(report)
    dataset_summary = _dataset_summary(report)

    metric_cards = [
        ("Stocks", _format_metric_value(report.get("stock_count"))),
        ("Rows", _format_metric_value(report.get("row_count"))),
        ("Latest Date", report.get("latest_trading_date")),
        ("Date Range", f"{report.get('date_range', {}).get('start')} to {report.get('date_range', {}).get('end')}"),
    ]

    cards_html = "\n".join(
        f"<div class='metric'><span>{html.escape(str(label))}</span><strong>{html.escape(str(value))}</strong></div>"
        for label, value in metric_cards
    )
    missing_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{float(value):.2%}</td></tr>"
        for key, value in missing.items()
    )
    coverage_html = "\n".join(
        "<tr><td>{ts_code}</td><td>{rows}</td><td>{start_date}</td><td>{end_date}</td><td>{coverage_ratio:.2%}</td></tr>".format(
            ts_code=_stock_code_link(item.get("ts_code"), _stock_name_for(item, stock_names)),
            rows=html.escape(str(item.get("rows", ""))),
            start_date=html.escape(str(item.get("start_date", ""))),
            end_date=html.escape(str(item.get("end_date", ""))),
            coverage_ratio=float(item.get("coverage_ratio", 0.0)),
        )
        for item in coverage
    )
    snapshot_html = "\n".join(
        "<tr><td>{ts_code}</td><td>{close}</td><td>{revenue}</td><td>{net_profit}</td><td>{roe}</td><td>{pe}</td><td>{pb}</td><td>{market_cap}</td></tr>".format(
            ts_code=_stock_code_link(row.get("ts_code"), _stock_name_for(row, stock_names)),
            **{key: html.escape(str(row.get(key, ""))) for key in ["close", "revenue", "net_profit", "roe", "pe", "pb", "market_cap"]},
        )
        for row in snapshot
    )

    factor_section = _render_factor_section(factor_report, stock_names, model_version=model_version)
    screener_section = _render_screener_section(screener_report, stock_names, model_version=model_version)
    backtest_section = _render_backtest_section(backtest_report, stock_names)
    optimization_section = _render_optimization_section(optimization_report)
    monetization_section = _render_monetization_section(monetization_report)
    structural_section = _render_structural_section(structural_report)
    regime_section = _render_regime_section(regime_report)
    behavior_section = _render_behavior_section(behavior_report)
    structure_section = _render_structure_section(structure_report)
    anomaly_section = _render_anomaly_section(anomaly_report)
    api_catalog_section = _render_api_catalog_section(_build_api_catalog())

    model_title = "TenBagger Model V2" if model_version == "v2" else "TenBagger Model V1"
    model_subtitle = "默认模型：Model V2 评分引擎" if model_version == "v2" else "历史模型：Model V1 评分引擎"
    model_nav = _model_nav(model_version)
    legacy_model_sections = (
        f"{backtest_section}{optimization_section}{monetization_section}{structural_section}"
        if model_version == "v1"
        else ""
    )

    content = f"""
    <main class="shell">
      <header class="topbar">
        <div>
          <h1>{model_title}</h1>
          <p>{model_subtitle}</p>
          {model_nav}
        </div>
        <div class="topbar-side">
          <div class="dataset-badge">{dataset_summary}</div>
          <div class="stamp">Generated {html.escape(str(report.get("generated_at")))}</div>
        </div>
      </header>
      <section class="metrics">{cards_html}</section>
      <section class="grid">
        <div>
          <h2>Missing Rates</h2>
          <table><thead><tr><th>Column</th><th>Missing</th></tr></thead><tbody>{missing_html}</tbody></table>
        </div>
        <div class="coverage-card">
          <h2>Stock Coverage</h2>
          <div class="table-scroll coverage-scroll">
            <table><thead><tr><th>Code</th><th>Rows</th><th>Start</th><th>End</th><th>Coverage</th></tr></thead><tbody>{coverage_html}</tbody></table>
          </div>
        </div>
      </section>
      <section>
        <h2>Latest Snapshot</h2>
        <table><thead><tr><th>Code</th><th>Close</th><th>Revenue</th><th>Net Profit</th><th>ROE</th><th>PE</th><th>PB</th><th>Market Cap</th></tr></thead><tbody>{snapshot_html}</tbody></table>
      </section>
      {factor_section}
      {screener_section}
      {legacy_model_sections}
      {regime_section}
      {behavior_section}
      {structure_section}
      {anomaly_section}
      {api_catalog_section}
    </main>
    """
    return _page(content)


def _render_api_catalog_section(catalog: dict[str, Any]) -> str:
    entry_html = "\n".join(
        "<tr><td>{path}</td><td>{reason}</td></tr>".format(
            path=html.escape(str(item.get("path", ""))),
            reason=html.escape(str(item.get("reason", ""))),
        )
        for item in catalog.get("recommended_entrypoints", [])
    )
    group_html = "\n".join(
        "<tr><td>{name}</td><td>{count}</td><td>{description}</td></tr>".format(
            name=html.escape(str(group.get("name", ""))),
            count=html.escape(str(len(group.get("endpoints", [])))),
            description=html.escape(str(group.get("description", ""))),
        )
        for group in catalog.get("groups", [])
    )
    safety = catalog.get("safety", {})
    non_read_only = safety.get("non_read_only_endpoints", [])
    non_read_only_text = "; ".join(
        f"{item.get('method')} {item.get('path')}: {item.get('reason')}" for item in non_read_only
    ) or "None"
    return f"""
    <section>
      <h2>接口说明</h2>
      <p>Total endpoints: {html.escape(str(catalog.get("total_endpoints")))}</p>
      <p>Catalog: <a href="/api">GET /api</a> | Docs: <a href="/docs">/docs</a> · <a href="/redoc">/redoc</a> · <a href="/openapi.json">/openapi.json</a></p>
    </section>
    <section class="grid">
      <div>
        <h2>Recommended Entrypoints</h2>
        <table><thead><tr><th>Path</th><th>Reason</th></tr></thead><tbody>{entry_html}</tbody></table>
      </div>
      <div>
        <h2>API Groups</h2>
        <table><thead><tr><th>Group</th><th>Endpoints</th><th>Description</th></tr></thead><tbody>{group_html}</tbody></table>
      </div>
    </section>
    <section>
      <h2>Safety Boundary</h2>
      <p>{html.escape(str(safety.get("default_boundary", "")))}</p>
      <p>{html.escape(str(safety.get("trading_boundary", "")))}</p>
      <p>Non-read-only: {html.escape(non_read_only_text)}</p>
    </section>
    """


def _render_factor_section(
    report: dict[str, Any] | None,
    stock_names: dict[str, str],
    model_version: str = "v2",
) -> str:
    if report is None:
        title = "Model V2 Factor Engine" if model_version == "v2" else "Model V1 Factor Engine"
        return """
        <section>
          <h2>{title}</h2>
          <table><tbody><tr><td>TASK 2 report not found</td></tr></tbody></table>
        </section>
        """.format(title=title)

    validation = report.get("validation", {})
    top_scores = report.get("latest_top_scores", [])
    model_v2 = report.get("model_v2_summary", {})
    top_scores_v2 = report.get("latest_top_scores_v2", [])
    score_distribution = report.get("score_distribution", {})
    validation_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>"
        for key, value in validation.items()
    )
    v2_validation = {
        "future_leak_rows": validation.get("future_leak_rows"),
        "nan_cells": validation.get("nan_cells"),
    }
    v2_score_distribution = score_distribution.get("tenbagger_score_v2", {})
    if isinstance(v2_score_distribution, dict):
        v2_validation.update(
            {
                "v2_score_std": v2_score_distribution.get("std"),
                "v2_score_min": v2_score_distribution.get("min"),
                "v2_score_max": v2_score_distribution.get("max"),
            }
        )
    v2_validation_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>"
        for key, value in v2_validation.items()
    )
    scores_html = "\n".join(
        "<tr><td>{ts_code}</td><td>{tenbagger_score}</td><td>{growth_score}</td><td>{quality_score}</td><td>{value_score}</td><td>{risk_score}</td><td>{momentum_score}</td></tr>".format(
            ts_code=_stock_code_link(row.get("ts_code"), _stock_name_for(row, stock_names)),
            **{key: html.escape(str(row.get(key, ""))) for key in ["tenbagger_score", "growth_score", "quality_score", "value_score", "risk_score", "momentum_score"]},
        )
        for row in top_scores
    )
    v2_summary_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>"
        for key, value in model_v2.items()
        if key != "grade_distribution"
    )
    v2_scores_html = "\n".join(
        "<tr><td>{ts_code}</td><td>{tenbagger_score_v2}</td><td>{v2_confidence_grade}</td><td>{v2_eligible}</td><td>{v2_weight_profile}</td></tr>".format(
            ts_code=_stock_code_link(row.get("ts_code"), _stock_name_for(row, stock_names)),
            **{
                key: html.escape(str(row.get(key, "")))
                for key in [
                    "tenbagger_score_v2",
                    "v2_confidence_grade",
                    "v2_eligible",
                    "v2_weight_profile",
                ]
            },
        )
        for row in top_scores_v2
    )
    if model_version == "v1":
        return f"""
        <section>
          <h2>Model V1 Factor Engine</h2>
        </section>
        <section class="grid">
          <div>
            <h2>Factor Validation</h2>
            <table><thead><tr><th>Check</th><th>Value</th></tr></thead><tbody>{validation_html}</tbody></table>
          </div>
          <div>
            <h2>Latest V1 Factor Scores</h2>
            <table><thead><tr><th>Code</th><th>TenBagger</th><th>Growth</th><th>Quality</th><th>Value</th><th>Risk</th><th>Momentum</th></tr></thead><tbody>{scores_html}</tbody></table>
          </div>
        </section>
        """

    return f"""
    <section>
      <h2>Model V2 Factor Engine</h2>
    </section>
    <section class="grid">
      <div>
        <h2>Model V2 Validation</h2>
        <table><thead><tr><th>Check</th><th>Value</th></tr></thead><tbody>{v2_validation_html}</tbody></table>
      </div>
      <div>
        <h2>Model V2 Summary</h2>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{v2_summary_html}</tbody></table>
      </div>
    </section>
    <section>
      <h2>Latest V2 Scores</h2>
      <table><thead><tr><th>Code</th><th>V2 Score</th><th>Grade</th><th>Eligible</th><th>Profile</th></tr></thead><tbody>{v2_scores_html}</tbody></table>
    </section>
    """


def _render_screener_section(
    report: dict[str, Any] | None,
    stock_names: dict[str, str],
    model_version: str = "v2",
) -> str:
    if report is None:
        title = "Model V2 Screener" if model_version == "v2" else "Model V1 Screener"
        return """
        <section>
          <h2>{title}</h2>
          <table><tbody><tr><td>TASK 3 report not found</td></tr></tbody></table>
        </section>
        """.format(title=title)

    preview = report.get("backtest_preview", {})
    v2_preview = report.get("v2_backtest_preview", {})
    decay = report.get("ic_decay_curve", [])
    v2_decay = report.get("v2_ic_decay_curve", [])
    candidates = report.get("top_candidates", [])
    near_misses = report.get("near_misses", [])
    v2_candidates = report.get("v2_top_candidates", [])
    model_v2 = report.get("model_v2_summary", {})

    preview_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>"
        for key, value in preview.items()
    )
    v2_preview_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>"
        for key, value in v2_preview.items()
    )
    decay_html = "\n".join(
        "<tr><td>{horizon_days}</td><td>{ic_mean}</td><td>{rank_ic_mean}</td><td>{observations}</td></tr>".format(
            **{key: html.escape(str(row.get(key, ""))) for key in ["horizon_days", "ic_mean", "rank_ic_mean", "observations"]}
        )
        for row in decay
    )
    v2_decay_html = "\n".join(
        "<tr><td>{horizon_days}</td><td>{ic_mean}</td><td>{rank_ic_mean}</td><td>{observations}</td></tr>".format(
            **{key: html.escape(str(row.get(key, ""))) for key in ["horizon_days", "ic_mean", "rank_ic_mean", "observations"]}
        )
        for row in v2_decay
    )
    candidate_rows = candidates or near_misses
    candidate_title = "V1 Top Candidates" if candidates else "V1 Near Misses"
    candidate_html = "\n".join(
        "<tr><td>{ts_code}</td><td>{tenbagger_score}</td><td>{industry}</td><td>{revenue_growth_yoy}</td><td>{roe}</td><td>{debt_ratio}</td><td>{fail_reasons}</td></tr>".format(
            ts_code=_stock_code_link(row.get("ts_code"), _stock_name_for(row, stock_names)),
            **{key: html.escape(str(row.get(key, ""))) for key in ["tenbagger_score", "industry", "revenue_growth_yoy", "roe", "debt_ratio", "fail_reasons"]},
        )
        for row in candidate_rows
    )
    v2_summary_bits = " | ".join(
        f"{html.escape(str(key))}: {html.escape(str(value))}"
        for key, value in model_v2.items()
        if key != "grade_distribution"
    )
    v2_candidate_html = "\n".join(
        "<tr><td>{ts_code}</td><td>{tenbagger_score_v2}</td><td>{v2_confidence_grade}</td><td>{v2_weight_profile}</td><td>{industry}</td><td>{v2_fail_reasons}</td></tr>".format(
            ts_code=_stock_code_link(row.get("ts_code"), _stock_name_for(row, stock_names)),
            **{
                key: html.escape(str(row.get(key, "")))
                for key in [
                    "tenbagger_score_v2",
                    "v2_confidence_grade",
                    "v2_weight_profile",
                    "industry",
                    "v2_fail_reasons",
                ]
            },
        )
        for row in v2_candidates
    )
    if model_version == "v1":
        return f"""
        <section>
          <h2>Model V1 Screener</h2>
          <p>Candidate count: {html.escape(str(report.get("candidate_count")))}</p>
        </section>
        <section class="grid">
          <div>
            <h2>V1 Backtest Preview</h2>
            <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{preview_html}</tbody></table>
          </div>
          <div>
            <h2>V1 IC Decay</h2>
            <table><thead><tr><th>Days</th><th>IC</th><th>RankIC</th><th>Obs</th></tr></thead><tbody>{decay_html}</tbody></table>
          </div>
        </section>
        <section>
          <h2>{candidate_title}</h2>
          <table><thead><tr><th>Code</th><th>Score</th><th>Industry</th><th>Growth</th><th>ROE</th><th>Debt</th><th>Fail Reasons</th></tr></thead><tbody>{candidate_html}</tbody></table>
        </section>
        """

    return f"""
    <section>
      <h2>Model V2 Screener</h2>
      <p>{v2_summary_bits}</p>
    </section>
    <section class="grid">
      <div>
        <h2>V2 Backtest Preview</h2>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{v2_preview_html}</tbody></table>
      </div>
      <div>
        <h2>V2 IC Decay</h2>
        <table><thead><tr><th>Days</th><th>IC</th><th>RankIC</th><th>Obs</th></tr></thead><tbody>{v2_decay_html}</tbody></table>
      </div>
    </section>
    <section>
      <h2>V2 Candidates</h2>
      <table><thead><tr><th>Code</th><th>V2 Score</th><th>Grade</th><th>Profile</th><th>Industry</th><th>Fail Reasons</th></tr></thead><tbody>{v2_candidate_html}</tbody></table>
    </section>
    """


def _render_backtest_section(report: dict[str, Any] | None, stock_names: dict[str, str]) -> str:
    if report is None:
        return """
        <section>
          <h2>Portfolio Backtest</h2>
          <table><tbody><tr><td>TASK 4 report not found</td></tr></tbody></table>
        </section>
        """

    metrics = report.get("metrics", {})
    benchmarks = metrics.get("benchmarks", {})
    attribution = report.get("factor_attribution", {})
    holdings = report.get("latest_holdings", [])
    provenance = _model_provenance_note(report, "v1", "tenbagger_score")
    date_range = report.get("date_range", {})
    config = report.get("config", {})
    backtest_period = f"{date_range.get('start', '')} to {date_range.get('end', '')}"
    backtest_details = [
        ("Backtest Period", backtest_period if backtest_period != " to " else ""),
        ("Rebalance", config.get("rebalance")),
        ("Rebalances", report.get("rebalance_count")),
    ]
    backtest_details_html = " | ".join(
        f"{html.escape(str(label))}: {html.escape(str(value))}"
        for label, value in backtest_details
        if value not in (None, "")
    )

    metric_keys = [
        "annual_return",
        "sharpe",
        "max_drawdown",
        "volatility",
        "win_rate",
        "turnover_rate",
        "total_transaction_cost",
    ]
    metrics_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(metrics.get(key, '')))}</td></tr>"
        for key in metric_keys
    )
    benchmark_html = "\n".join(
        "<tr><td>{name}</td><td>{annual_return}</td><td>{excess_return}</td><td>{beta}</td><td>{max_drawdown}</td></tr>".format(
            name=html.escape(str(name)),
            **{key: html.escape(str(value.get(key, ""))) for key in ["annual_return", "excess_return", "beta", "max_drawdown"]},
        )
        for name, value in benchmarks.items()
    )
    holding_html = "\n".join(
        "<tr><td>{ts_code}</td><td>{weight}</td><td>{rebalance_date}</td></tr>".format(
            ts_code=_stock_code_link(row.get("ts_code"), _stock_name_for(row, stock_names)),
            **{key: html.escape(str(row.get(key, ""))) for key in ["weight", "rebalance_date"]},
        )
        for row in holdings
    )
    return f"""
    <section>
      <h2>Portfolio Backtest</h2>
      <p>{provenance}</p>
      <p>{backtest_details_html}</p>
      <p>Final NAV: {html.escape(str(report.get("final_nav")))} | Dominant factor: {html.escape(str(attribution.get("dominant_factor")))}</p>
    </section>
    <section class="grid">
      <div>
        <h2>Risk Metrics</h2>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{metrics_html}</tbody></table>
      </div>
      <div>
        <h2>Benchmarks</h2>
        <table><thead><tr><th>Name</th><th>Annual</th><th>Excess</th><th>Beta</th><th>Drawdown</th></tr></thead><tbody>{benchmark_html}</tbody></table>
      </div>
    </section>
    <section>
      <h2>Latest Holdings</h2>
      <table><thead><tr><th>Code</th><th>Weight</th><th>Rebalance Date</th></tr></thead><tbody>{holding_html}</tbody></table>
    </section>
    """


def _render_optimization_section(report: dict[str, Any] | None) -> str:
    if report is None:
        return """
        <section>
          <h2>Factor Optimization</h2>
          <table><tbody><tr><td>TASK 5 report not found</td></tr></tbody></table>
        </section>
        """

    baseline = report.get("baseline_test_metrics", {})
    optimized = report.get("test_metrics", {})
    weights = report.get("best_weights", {})
    ic = report.get("ic_comparison", {})
    provenance = _model_provenance_note(report, "v1_optimized", "tenbagger_score")
    weight_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>"
        for key, value in weights.items()
    )
    metrics_html = "\n".join(
        "<tr><td>{metric}</td><td>{base}</td><td>{opt}</td></tr>".format(
            metric=html.escape(metric),
            base=html.escape(str(baseline.get(metric, ""))),
            opt=html.escape(str(optimized.get(metric, ""))),
        )
        for metric in ["annual_return", "sharpe", "max_drawdown", "volatility", "win_rate"]
    )
    ic_html = "\n".join(
        "<tr><td>{key}</td><td>{baseline_rank_ic}</td><td>{optimized_rank_ic}</td><td>{delta}</td></tr>".format(
            key=html.escape(str(key)),
            **{field: html.escape(str(value.get(field, ""))) for field in ["baseline_rank_ic", "optimized_rank_ic", "delta"]},
        )
        for key, value in ic.items()
    )
    return f"""
    <section>
      <h2>Factor Optimization</h2>
      <p>{provenance}</p>
      <p>Candidates evaluated: {html.escape(str(report.get("candidates_evaluated")))}</p>
    </section>
    <section class="grid">
      <div>
        <h2>Best Weights</h2>
        <table><thead><tr><th>Factor</th><th>Weight</th></tr></thead><tbody>{weight_html}</tbody></table>
      </div>
      <div>
        <h2>Baseline vs Optimized</h2>
        <table><thead><tr><th>Metric</th><th>Baseline</th><th>Optimized</th></tr></thead><tbody>{metrics_html}</tbody></table>
      </div>
    </section>
    <section>
      <h2>IC Improvement</h2>
      <table><thead><tr><th>Horizon</th><th>Baseline RankIC</th><th>Optimized RankIC</th><th>Delta</th></tr></thead><tbody>{ic_html}</tbody></table>
    </section>
    """


def _render_monetization_section(report: dict[str, Any] | None) -> str:
    if report is None:
        return """
        <section>
          <h2>Alpha Monetization</h2>
          <table><tbody><tr><td>TASK 6 report not found</td></tr></tbody></table>
        </section>
        """

    best = report.get("best_config", {})
    test = report.get("test_metrics", {})
    divergence = report.get("ic_pnl_divergence", {})
    costs = report.get("cost_sensitivity", [])
    provenance = _model_provenance_note(report, "v1_optimized", "tenbagger_score")
    best_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>"
        for key, value in best.items()
    )
    test_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(test.get(key, '')))}</td></tr>"
        for key in ["annual_return", "sharpe", "max_drawdown", "turnover_rate"]
    )
    cost_html = "\n".join(
        "<tr><td>{transaction_cost_rate}</td><td>{sharpe}</td><td>{annual_return}</td><td>{turnover_rate}</td></tr>".format(
            **{key: html.escape(str(row.get(key, ""))) for key in ["transaction_cost_rate", "sharpe", "annual_return", "turnover_rate"]}
        )
        for row in costs
    )
    return f"""
    <section>
      <h2>Alpha Monetization</h2>
      <p>{provenance}</p>
      <p>{html.escape(str(divergence.get("interpretation")))}</p>
    </section>
    <section class="grid">
      <div>
        <h2>Best Config</h2>
        <table><thead><tr><th>Setting</th><th>Value</th></tr></thead><tbody>{best_html}</tbody></table>
      </div>
      <div>
        <h2>Test Metrics</h2>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{test_html}</tbody></table>
      </div>
    </section>
    <section>
      <h2>Cost Sensitivity</h2>
      <table><thead><tr><th>Cost</th><th>Sharpe</th><th>Annual</th><th>Turnover</th></tr></thead><tbody>{cost_html}</tbody></table>
    </section>
    """


def _render_structural_section(report: dict[str, Any] | None) -> str:
    if report is None:
        return """
        <section>
          <h2>Structural Validation</h2>
          <table><tbody><tr><td>TASK 7 report not found</td></tr></tbody></table>
        </section>
        """

    criteria = report.get("criteria", {})
    stability = report.get("stability_report", {})
    randomization = report.get("randomization_test", {})
    failure = report.get("failure_mode_diagnosis", {})
    metrics = report.get("oos_metrics", {})
    provenance = _model_provenance_note(report, "v1", "tenbagger_score")
    criteria_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>"
        for key, value in criteria.items()
    )
    stability_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(stability.get(key, '')))}</td></tr>"
        for key in ["score", "ic_variance", "sharpe_variance", "positive_sharpe_ratio", "decay_slow"]
    )
    random_html = "\n".join(
        "<tr><td>{name}</td><td>{mean}</td><td>{p95}</td><td>{p_value}</td><td>{significant}</td></tr>".format(
            name=html.escape(str(name)),
            **{key: html.escape(str(value.get(key, ""))) for key in ["mean", "p95", "p_value", "significant"]},
        )
        for name, value in {
            "label_shuffle": randomization.get("label_shuffle", {}),
            "feature_permutation": randomization.get("feature_permutation", {}),
        }.items()
    )
    metric_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(metrics.get(key, '')))}</td></tr>"
        for key in ["annual_return", "sharpe", "max_drawdown", "turnover_rate"]
    )
    return f"""
    <section>
      <h2>Structural Validation</h2>
      <p>{provenance}</p>
      <p>Classification: {html.escape(str(report.get("classification")))} | Primary failure: {html.escape(str(failure.get("primary_failure")))}</p>
    </section>
    <section class="grid">
      <div>
        <h2>OOS Metrics</h2>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{metric_html}</tbody></table>
      </div>
      <div>
        <h2>Stability</h2>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{stability_html}</tbody></table>
      </div>
    </section>
    <section class="grid">
      <div>
        <h2>Real Alpha Criteria</h2>
        <table><thead><tr><th>Criterion</th><th>Value</th></tr></thead><tbody>{criteria_html}</tbody></table>
      </div>
      <div>
        <h2>Randomization</h2>
        <table><thead><tr><th>Test</th><th>Mean</th><th>P95</th><th>P Value</th><th>Significant</th></tr></thead><tbody>{random_html}</tbody></table>
      </div>
    </section>
    """


def _render_regime_section(report: dict[str, Any] | None) -> str:
    if report is None:
        return """
        <section>
          <h2>Market Regime Dashboard</h2>
          <table><tbody><tr><td>TASK 8 report not found</td></tr></tbody></table>
        </section>
        """

    latest = report.get("latest", {})
    api = report.get("api_response", {})
    validation = report.get("validation", {})
    history = report.get("history", {})
    chart_tail = history.get("chart_tail", [])
    recent_changes = history.get("recent_30_changes", [])

    metric_cards = [
        ("Behavior", api.get("behavior_state")),
        ("Trend", api.get("trend_regime")),
        ("Volatility", api.get("volatility_regime")),
        ("Liquidity", api.get("liquidity_regime")),
    ]
    cards_html = "\n".join(
        f"<div class='metric'><span>{html.escape(str(label))}</span><strong>{html.escape(str(value))}</strong></div>"
        for label, value in metric_cards
    )
    detail_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(_fmt(latest.get(key)))}</td></tr>"
        for key in [
            "date",
            "trend_strength",
            "volatility_percentile",
            "liquidity_score",
            "regime_change_probability",
            "stability_score",
        ]
    )
    validation_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(_fmt(validation.get(key)))}</td></tr>"
        for key in [
            "regime_autocorrelation",
            "transition_frequency",
            "recent_30d_transition_frequency",
            "mean_duration_days",
            "transition_not_overfit",
            "regime_has_continuity",
        ]
    )
    change_html = "\n".join(
        "<tr><td>{date}</td><td>{trend_regime}</td><td>{volatility_regime}</td><td>{liquidity_regime}</td><td>{behavior_state}</td></tr>".format(
            **{key: html.escape(str(row.get(key, ""))) for key in ["date", "trend_regime", "volatility_regime", "liquidity_regime", "behavior_state"]}
        )
        for row in recent_changes[-10:]
    )
    if not change_html:
        change_html = "<tr><td colspan='5'>No regime changes in the latest 30 observations</td></tr>"

    regime_strip = _regime_strip(chart_tail)
    trend_chart = _sparkline_svg(chart_tail, "trend_strength", "#0f766e")
    volatility_chart = _sparkline_svg(chart_tail, "realized_vol_20d", "#9f1239")
    liquidity_chart = _sparkline_svg(chart_tail, "liquidity_score", "#1d4ed8")

    return f"""
    <section>
      <h2>Market Regime Dashboard</h2>
      <p>Behavioral state engine for route 2. Data source: {html.escape(str(report.get("data_source", {}).get("source")))}</p>
    </section>
    <section class="metrics">{cards_html}</section>
    <section>
      <h2>Behavior State History</h2>
      <p>这里显示近期 behavior_state 的变化，不表示牛市早中晚阶段。</p>
      {regime_strip}
    </section>
    <section class="grid">
      <div>
        <h2>Current Regime Detail</h2>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{detail_html}</tbody></table>
      </div>
      <div>
        <h2>Regime Validation</h2>
        <table><thead><tr><th>Check</th><th>Value</th></tr></thead><tbody>{validation_html}</tbody></table>
      </div>
    </section>
    <section class="grid">
      <div>
        <h2>Trend Strength</h2>
        {trend_chart}
      </div>
      <div>
        <h2>Volatility Curve</h2>
        {volatility_chart}
      </div>
    </section>
    <section>
      <h2>Liquidity Curve</h2>
      {liquidity_chart}
    </section>
    <section>
      <h2>Recent Regime Changes</h2>
      <table><thead><tr><th>Date</th><th>Trend</th><th>Volatility</th><th>Liquidity</th><th>Behavior</th></tr></thead><tbody>{change_html}</tbody></table>
    </section>
    """


def _render_behavior_section(report: dict[str, Any] | None) -> str:
    if report is None:
        return """
        <section>
          <h2>Behavioral Flow Dashboard</h2>
          <table><tbody><tr><td>TASK 9 report not found</td></tr></tbody></table>
        </section>
        """

    latest = report.get("latest", {})
    api = report.get("api_response", {})
    validation = report.get("validation", {})
    history = report.get("history", {})
    chart_tail = history.get("chart_tail", [])
    divergence_events = history.get("divergence_events", [])

    metric_cards = [
        ("Actor", latest.get("dominant_actor")),
        ("Crowding", api.get("crowding_level")),
        ("Divergence", api.get("flow_price_divergence")),
        ("Overlay", api.get("behavior_overlay_state")),
    ]
    cards_html = "\n".join(
        f"<div class='metric'><span>{html.escape(str(label))}</span><strong>{html.escape(str(value))}</strong></div>"
        for label, value in metric_cards
    )
    detail_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(_fmt(latest.get(key)))}</td></tr>"
        for key in [
            "date",
            "retail_pressure_index",
            "institutional_flow_index",
            "panic_index",
            "fomo_index",
            "positioning_crowdedness",
            "reversal_risk",
            "joint_regime_behavior",
        ]
    )
    validation_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(_fmt(validation.get(key)))}</td></tr>"
        for key in [
            "uses_future_return_labels",
            "uses_factor_alpha",
            "all_scores_bounded_0_1",
            "overlay_autocorrelation",
            "behavior_transition_frequency",
            "divergence_event_frequency",
            "recent_30d_mean_panic",
            "recent_30d_mean_fomo",
        ]
    )
    event_html = "\n".join(
        "<tr><td>{date}</td><td>{flow_price_divergence}</td><td>{divergence_score}</td><td>{dominant_actor}</td><td>{behavior_overlay_state}</td></tr>".format(
            **{key: html.escape(str(row.get(key, ""))) for key in ["date", "flow_price_divergence", "divergence_score", "dominant_actor", "behavior_overlay_state"]}
        )
        for row in divergence_events[-10:]
    )
    if not event_html:
        event_html = "<tr><td colspan='5'>No recent flow-price divergence events</td></tr>"

    retail_chart = _sparkline_svg(chart_tail, "retail_pressure_index", "#b45309")
    institutional_chart = _sparkline_svg(chart_tail, "institutional_flow_index", "#0f766e")
    panic_chart = _sparkline_svg(chart_tail, "panic_index", "#be123c")
    fomo_chart = _sparkline_svg(chart_tail, "fomo_index", "#1d4ed8")
    crowding_heatmap = _crowding_heatmap(chart_tail)

    return f"""
    <section>
      <h2>Behavioral Flow Dashboard</h2>
      <p>Market actors and behavior pressure. Source: {html.escape(str(report.get("source", {}).get("source")))}</p>
    </section>
    <section class="metrics">{cards_html}</section>
    <section>
      <h2>Crowding Heatmap</h2>
      {crowding_heatmap}
    </section>
    <section class="grid">
      <div>
        <h2>Behavior Detail</h2>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{detail_html}</tbody></table>
      </div>
      <div>
        <h2>Behavior Validation</h2>
        <table><thead><tr><th>Check</th><th>Value</th></tr></thead><tbody>{validation_html}</tbody></table>
      </div>
    </section>
    <section class="grid">
      <div>
        <h2>Retail Pressure</h2>
        {retail_chart}
      </div>
      <div>
        <h2>Institutional Flow</h2>
        {institutional_chart}
      </div>
    </section>
    <section class="grid">
      <div>
        <h2>Panic Timeline</h2>
        {panic_chart}
      </div>
      <div>
        <h2>FOMO Timeline</h2>
        {fomo_chart}
      </div>
    </section>
    <section>
      <h2>Flow-Price Divergence</h2>
      <table><thead><tr><th>Date</th><th>Divergence</th><th>Score</th><th>Actor</th><th>Overlay</th></tr></thead><tbody>{event_html}</tbody></table>
    </section>
    """


def _render_structure_section(report: dict[str, Any] | None) -> str:
    if report is None:
        return """
        <section>
          <h2>Market Structure Dashboard</h2>
          <table><tbody><tr><td>TASK 10 report not found</td></tr></tbody></table>
        </section>
        """

    latest = report.get("latest", {})
    api = report.get("api_response", {})
    validation = report.get("validation", {})
    history = report.get("history", {})
    chart_tail = history.get("chart_tail", [])
    shocks = history.get("structural_shocks", [])

    metric_cards = [
        ("Structure", api.get("structure_state")),
        ("Correlation", api.get("correlation_regime")),
        ("Dispersion", _fmt(api.get("market_dispersion"))),
        ("Shock", _fmt(api.get("structural_shock_probability"))),
    ]
    cards_html = "\n".join(
        f"<div class='metric'><span>{html.escape(str(label))}</span><strong>{html.escape(str(value))}</strong></div>"
        for label, value in metric_cards
    )
    detail_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(_fmt(latest.get(key)))}</td></tr>"
        for key in [
            "date",
            "trend_component",
            "flow_component",
            "volatility_component",
            "noise_component",
            "cross_sectional_correlation",
            "structural_shock_type",
            "regime_behavior_structure",
        ]
    )
    validation_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(_fmt(validation.get(key)))}</td></tr>"
        for key in [
            "uses_future_return_labels",
            "uses_alpha_factors",
            "purely_observational",
            "components_sum_to_one",
            "all_scores_bounded_0_1",
            "structure_autocorrelation",
            "structure_transition_frequency",
            "shock_event_frequency",
        ]
    )
    shock_html = "\n".join(
        "<tr><td>{date}</td><td>{structural_shock_type}</td><td>{structural_shock_probability}</td><td>{structure_state}</td></tr>".format(
            **{key: html.escape(str(row.get(key, ""))) for key in ["date", "structural_shock_type", "structural_shock_probability", "structure_state"]}
        )
        for row in shocks[-10:]
    )
    if not shock_html:
        shock_html = "<tr><td colspan='4'>No recent structural shock events</td></tr>"

    decomposition = _decomposition_bars(latest)
    dispersion_heatmap = _value_heatmap(chart_tail, "market_dispersion", "#dbeafe", "#1d4ed8")
    correlation_chart = _sparkline_svg(chart_tail, "cross_sectional_correlation", "#7c3aed")
    structure_timeline = _structure_strip(chart_tail)

    return f"""
    <section>
      <h2>Market Structure Dashboard</h2>
      <p>Structure decomposition across trend, flow, volatility, and noise. Source: {html.escape(str(report.get("source", {}).get("source")))}</p>
    </section>
    <section class="metrics">{cards_html}</section>
    <section>
      <h2>Return Decomposition</h2>
      {decomposition}
    </section>
    <section>
      <h2>Structure State Timeline</h2>
      {structure_timeline}
    </section>
    <section class="grid">
      <div>
        <h2>Structure Detail</h2>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{detail_html}</tbody></table>
      </div>
      <div>
        <h2>Structure Validation</h2>
        <table><thead><tr><th>Check</th><th>Value</th></tr></thead><tbody>{validation_html}</tbody></table>
      </div>
    </section>
    <section class="grid">
      <div>
        <h2>Dispersion Heatmap</h2>
        {dispersion_heatmap}
      </div>
      <div>
        <h2>Correlation Network</h2>
        {correlation_chart}
      </div>
    </section>
    <section>
      <h2>Structural Shock Events</h2>
      <table><thead><tr><th>Date</th><th>Type</th><th>Probability</th><th>State</th></tr></thead><tbody>{shock_html}</tbody></table>
    </section>
    """


def _render_anomaly_section(report: dict[str, Any] | None) -> str:
    if report is None:
        return """
        <section>
          <h2>Structural Anomaly Dashboard</h2>
          <table><tbody><tr><td>TASK 11 report not found</td></tr></tbody></table>
        </section>
        """

    latest = report.get("latest", {})
    api = report.get("api_response", {})
    validation = report.get("validation", {})
    history = report.get("history", {})
    chart_tail = history.get("chart_tail", [])
    anomaly_events = history.get("anomaly_events", [])
    flow_events = history.get("flow_shock_events", [])

    metric_cards = [
        ("Risk", api.get("systemic_risk_level")),
        ("Anomaly", _fmt(api.get("anomaly_score"))),
        ("Dominant", api.get("dominant_anomaly_type")),
        ("State", api.get("anomaly_state")),
    ]
    cards_html = "\n".join(
        f"<div class='metric'><span>{html.escape(str(label))}</span><strong>{html.escape(str(value))}</strong></div>"
        for label, value in metric_cards
    )
    detail_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(_fmt(latest.get(key)))}</td></tr>"
        for key in [
            "date",
            "structural_break_prob",
            "correlation_break_prob",
            "flow_shock_prob",
            "behavioral_anomaly_score",
            "cross_sector_decoupling_prob",
            "liquidity_vacuum_prob",
        ]
    )
    validation_html = "\n".join(
        f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(_fmt(validation.get(key)))}</td></tr>"
        for key in [
            "uses_future_return_labels",
            "uses_alpha_model",
            "predicts_market_direction",
            "purely_observational",
            "all_scores_bounded_0_1",
            "anomaly_event_frequency",
            "high_risk_frequency",
            "recent_30d_mean_anomaly",
        ]
    )
    event_html = "\n".join(
        "<tr><td>{date}</td><td>{anomaly_state}</td><td>{anomaly_score}</td><td>{systemic_risk_level}</td></tr>".format(
            **{key: html.escape(str(row.get(key, ""))) for key in ["date", "anomaly_state", "anomaly_score", "systemic_risk_level"]}
        )
        for row in anomaly_events[-10:]
    )
    if not event_html:
        event_html = "<tr><td colspan='4'>No medium/high anomaly events in latest 120 observations</td></tr>"
    flow_html = "\n".join(
        "<tr><td>{date}</td><td>{flow_shock_prob}</td><td>{institutional_flow_shock_prob}</td><td>{retail_panic_cluster_prob}</td></tr>".format(
            **{key: html.escape(str(row.get(key, ""))) for key in ["date", "flow_shock_prob", "institutional_flow_shock_prob", "retail_panic_cluster_prob"]}
        )
        for row in flow_events[-10:]
    )
    if not flow_html:
        flow_html = "<tr><td colspan='4'>No recent flow shock events</td></tr>"

    anomaly_chart = _sparkline_svg(chart_tail, "anomaly_score", "#be123c")
    shock_heatmap = _value_heatmap(chart_tail, "anomaly_score", "#fee2e2", "#be123c")
    correlation_chart = _sparkline_svg(chart_tail, "correlation_break_prob", "#7c3aed")
    anomaly_strip = _anomaly_strip(chart_tail)

    return f"""
    <section>
      <h2>Structural Anomaly Dashboard</h2>
      <p>Purely observational anomaly detection across regime, behavior, and structure. Source: {html.escape(str(report.get("source", {}).get("source")))}</p>
    </section>
    <section class="metrics">{cards_html}</section>
    <section>
      <h2>Anomaly Timeline</h2>
      {anomaly_chart}
    </section>
    <section>
      <h2>Shock Detection Heatmap</h2>
      {shock_heatmap}
    </section>
    <section>
      <h2>Anomaly State Timeline</h2>
      {anomaly_strip}
    </section>
    <section class="grid">
      <div>
        <h2>Anomaly Detail</h2>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{detail_html}</tbody></table>
      </div>
      <div>
        <h2>Anomaly Validation</h2>
        <table><thead><tr><th>Check</th><th>Value</th></tr></thead><tbody>{validation_html}</tbody></table>
      </div>
    </section>
    <section class="grid">
      <div>
        <h2>Correlation Breakdown</h2>
        {correlation_chart}
      </div>
      <div>
        <h2>Flow Shock Events</h2>
        <table><thead><tr><th>Date</th><th>Flow</th><th>Inst</th><th>Retail</th></tr></thead><tbody>{flow_html}</tbody></table>
      </div>
    </section>
    <section>
      <h2>Anomaly Events</h2>
      <table><thead><tr><th>Date</th><th>State</th><th>Score</th><th>Risk</th></tr></thead><tbody>{event_html}</tbody></table>
    </section>
    """


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _format_metric_value(value: Any) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _dataset_summary(report: dict[str, Any]) -> str:
    storage = report.get("storage", {})
    universe = storage.get("universe", {}) if isinstance(storage, dict) else {}
    level = report.get("universe_level") or universe.get("level") or "unknown"
    universe_count = report.get("universe_count") or universe.get("stock_count")
    loaded_count = report.get("stock_count")
    source = storage.get("source") if isinstance(storage, dict) else None
    source_text = str(source or "local").upper()
    return html.escape(f"当前数据集：{level} 股票池 · 目标 {universe_count} 只 · 已加载 {loaded_count} 只 · {source_text}")


def _model_nav(model_version: str) -> str:
    if model_version == "v1":
        return """
        <nav class="model-nav" aria-label="Model versions">
          <a href="/">返回 Model V2</a>
          <span class="active">Model V1</span>
        </nav>
        """
    return """
    <nav class="model-nav" aria-label="Model versions">
      <span class="active">Model V2</span>
      <a href="/model/v1">查看 Model V1</a>
    </nav>
    """


def _model_provenance_note(
    report: dict[str, Any],
    default_model: str,
    default_score_column: str,
) -> str:
    provenance = report.get("model_provenance", {})
    if not isinstance(provenance, dict):
        provenance = {}
    model = provenance.get("model_version") or default_model
    score_column = provenance.get("score_column") or default_score_column
    note = provenance.get("note") or "Legacy model chain."
    return html.escape(f"Model source: {model} · Score column: {score_column} · {note}")


HELP_TEXT = {
    "TenBagger": "十倍股寻找系统：把数据质量、因子打分、筛选、回测和市场结构研究放在一个页面里。",
    "TenBagger Model V2": "当前默认模型页面：只展示 Model V2 相关评分、验证和候选池。",
    "TenBagger Model V1": "历史模型页面：用于回看旧版 V1 评分和候选池。",
    "Model V2": "当前默认模型。V2 加入硬门槛、动态权重、置信等级和市场状态。",
    "Model V1": "历史模型。保留用于对照，不再作为默认页面。",
    "Model V2 Factor Engine": "V2 因子引擎：当前默认评分模型。",
    "Model V1 Factor Engine": "V1 因子引擎：旧版评分模型，仅用于回看和对照。",
    "Model V2 Screener": "V2 筛选器：只展示 V2 回测预览、V2 IC 和 V2 候选池。",
    "Model V1 Screener": "V1 筛选器：旧版候选池页面，仅用于对照。",
    "Stocks": "当前数据集中覆盖的股票数量。",
    "Rows": "当前数据集中可用的日线或合并数据行数。",
    "Latest Date": "当前数据更新到的最近交易日。",
    "Date Range": "当前数据覆盖的起止日期。",
    "Missing Rates": "字段缺失率；越低说明基础数据越完整。",
    "Stock Coverage": "每只股票的数据覆盖情况，用来检查是否有缺口或样本太短。",
    "Latest Snapshot": "每只股票最近一个交易日的核心财务和估值快照。",
    "Factor Engine": "因子引擎：把成长、质量、估值、风险、动量等指标合成为十倍股评分。",
    "Factor Validation": "因子校验：检查打分是否存在未来函数、空值或异常分布。",
    "Model V2 Validation": "V2 专用校验：这里只显示 V2 分数分布和通用数据质量，不混入 V1 分数统计。",
    "Latest Factor Scores": "最近一期因子评分；分数越高，模型认为越符合十倍股特征。",
    "Latest V1 Factor Scores": "最近一期 V1 因子评分；仅用于旧模型回看。",
    "Model V2 Summary": "V2 评分引擎摘要：硬门槛、动态权重、置信等级的总体情况。",
    "Latest V2 Scores": "最近一期 V2 排名；默认页只展示 V2 结果，V1 对照请进入 Model V1 页面。",
    "V2 Score": "Model V2 综合分；已经考虑硬门槛、市场状态、行业相对排名和风险约束。",
    "Grade": "V2 置信等级：A 最强，B 可研究，C 观察，D 暂不可靠。",
    "Eligible": "是否通过 V2 硬门槛。",
    "Profile": "V2 当前使用的动态权重模式。",
    "Screener": "筛选器：用硬条件和评分选出候选股或接近候选的股票。",
    "Backtest Preview": "筛选结果的快速回测预览，只用于观察方向，不等同于交易建议。",
    "IC Decay": "信息系数衰减；看当前评分对未来不同周期收益排序的解释力。",
    "V1 Backtest Preview": "V1 排名的快速预览回测；仅用于旧模型对照。",
    "V1 IC Decay": "V1 分数的信息系数衰减；用于和 V2 对比。",
    "V2 Backtest Preview": "V2 排名的快速预览回测；用于和 V1 预览对比，不等同于交易建议。",
    "V2 IC Decay": "V2 分数的信息系数衰减；判断 V2 排名是否比 V1 更有解释力。",
    "V2 Candidates": "按 V2 分数和置信等级排序的候选研究清单。",
    "Top Candidates": "当前通过筛选条件的候选股。",
    "V1 Top Candidates": "V1 旧版硬筛选后的候选股。",
    "V1 Near Misses": "V1 旧版筛选中接近通过但仍未满足条件的股票。",
    "Near Misses": "接近通过但仍有条件未满足的股票。",
    "Portfolio Backtest": "组合回测：按模型规则构建组合后观察历史表现。",
    "Risk Metrics": "风险收益指标，用来评估组合波动、回撤和胜率。",
    "Benchmarks": "基准指数对照，用来判断组合是否跑赢市场。",
    "Latest Holdings": "回测规则在最近一次调仓时给出的模拟持仓权重。",
    "Factor Optimization": "因子权重优化：寻找更稳健的因子组合权重。",
    "Best Weights": "优化后选择的各因子权重。",
    "Baseline vs Optimized": "原始模型与优化后模型的指标对比。",
    "IC Improvement": "优化前后排序预测能力的变化。",
    "Alpha Monetization": "把因子信号转成组合收益的能力评估。",
    "Best Config": "在测试集中表现相对更好的组合参数。",
    "Test Metrics": "测试区间上的组合表现指标。",
    "Cost Sensitivity": "交易成本变化对收益和换手的影响。",
    "Structural Validation": "结构性验证：区分真实 alpha、伪 alpha 和无效信号。",
    "OOS Metrics": "样本外指标；用于看模型离开训练区间后是否仍有效。",
    "Stability": "稳定性检查；观察收益、IC 和夏普是否过度波动。",
    "Real Alpha Criteria": "判断信号是否可能是真实 alpha 的条件清单。",
    "Randomization": "随机化检验；通过打乱标签或特征验证结果是否只是巧合。",
    "Market Regime Dashboard": "市场状态面板：观察趋势、波动、流动性和行为状态。",
    "Behavior State History": "近期市场行为状态变化的时间条；不是牛市早中晚阶段。",
    "Current Regime Detail": "当前市场状态的细分指标。",
    "Regime Validation": "市场状态识别是否连续、稳定、不过度跳变的检查。",
    "Trend Strength": "趋势强度；越高表示上涨或下跌方向越清晰。",
    "Volatility Curve": "波动率曲线；越高表示市场波动越大。",
    "Liquidity Curve": "流动性曲线；越高表示成交和资金活跃度越好。",
    "Recent Regime Changes": "最近发生市场状态切换的日期和状态。",
    "Behavioral Flow Dashboard": "行为资金流面板：观察散户、机构、恐慌、追涨和拥挤度。",
    "Crowding Heatmap": "拥挤度热力图；颜色越强表示交易拥挤或反转风险越高。",
    "Behavior Detail": "行为层面的细分指标。",
    "Behavior Validation": "行为模型是否只用当时可见数据、分数是否合理的检查。",
    "Retail Pressure": "散户压力；偏高时说明短线情绪参与更强。",
    "Institutional Flow": "机构流向；偏高时说明机构资金特征更强。",
    "Panic Timeline": "恐慌时间线；偏高时说明避险或抛压情绪更强。",
    "FOMO Timeline": "追涨情绪时间线；偏高时说明错失恐惧和追高倾向更强。",
    "Flow-Price Divergence": "量价背离；资金行为和价格反应不一致时需要重点观察。",
    "Market Structure Dashboard": "市场结构面板：把趋势、资金流、波动和噪声拆开看。",
    "Return Decomposition": "收益结构分解；观察当前市场主要由什么因素驱动。",
    "Structure State Timeline": "市场结构状态的近期变化。",
    "Structure Detail": "结构模型的当前细分指标。",
    "Structure Validation": "结构模型是否纯观察、是否不用未来收益标签的检查。",
    "Dispersion Heatmap": "离散度热力图；看个股分化程度。",
    "Correlation Network": "相关性走势；越高表示个股更同步，越低表示分化更强。",
    "Structural Shock Events": "结构冲击事件；提示市场结构可能发生异常变化的日期。",
    "Structural Anomaly Dashboard": "结构异常面板：观察系统性风险、结构断裂、流动性真空等异常。",
    "Anomaly Timeline": "异常分数时间线；越高表示结构偏离常态越明显。",
    "Shock Detection Heatmap": "冲击检测热力图；颜色越强表示异常冲击概率越高。",
    "Anomaly State Timeline": "异常状态的近期变化。",
    "Anomaly Detail": "异常模型的当前细分指标。",
    "Anomaly Validation": "异常检测是否纯观察、是否不预测涨跌的检查。",
    "Correlation Breakdown": "相关性断裂概率；偏高时说明市场内部联动关系变化明显。",
    "Flow Shock Events": "资金流冲击事件；观察机构或散户流动是否出现异常。",
    "Anomaly Events": "中高风险异常事件清单。",
    "接口说明": "当前系统的公开接口目录入口；只做说明，不触发计算、写入或交易。",
    "Recommended Entrypoints": "建议优先使用的页面和 API 入口。",
    "API Groups": "按功能分组的公开接口数量。",
    "Safety Boundary": "接口安全边界，说明哪些接口只读、哪些接口可能写入本地报告。",
    "Path": "接口路径。",
    "Reason": "推荐使用该入口的原因。",
    "Group": "接口分组。",
    "Endpoints": "该分组下的接口数量。",
    "Description": "说明文字。",
    "Column": "数据字段名。",
    "Missing": "该字段缺失比例。",
    "Code": "股票代码；后面的 Xueqiu 可打开雪球页面。",
    "Close": "最近收盘价。",
    "Revenue": "营业收入。",
    "Net Profit": "净利润。",
    "ROE": "净资产收益率，衡量公司赚钱效率。",
    "PE": "市盈率，股价相对盈利的估值倍数。",
    "PB": "市净率，股价相对净资产的估值倍数。",
    "Market Cap": "总市值。",
    "Check": "校验项。",
    "Value": "该指标或校验项的当前值。",
    "Growth": "成长因子，关注收入和利润增长。",
    "Quality": "质量因子，关注盈利质量和财务稳健性。",
    "Risk": "风险项或风险等级；数值越高通常表示风险越高。",
    "Momentum": "动量因子，关注价格趋势延续性。",
    "Metric": "指标名称。",
    "Days": "观察周期天数。",
    "IC": "信息系数，衡量因子分数与未来收益的相关性。",
    "RankIC": "排序信息系数，衡量因子排序与未来收益排序的相关性。",
    "Obs": "有效样本数量。",
    "Score": "评分或概率数值。",
    "Industry": "所属行业。",
    "Debt": "负债率或债务压力指标。",
    "Fail Reasons": "未通过筛选条件的原因。",
    "Name": "基准或项目名称。",
    "Annual": "年化收益率。",
    "Excess": "相对基准的超额收益。",
    "Beta": "相对市场波动的敏感度。",
    "Drawdown": "最大回撤，表示从高点下跌的幅度。",
    "Weight": "组合中的模拟权重。",
    "Rebalance Date": "最近一次模拟调仓日期。",
    "Factor": "因子名称。",
    "Baseline": "优化前的基准模型。",
    "Optimized": "优化后的模型。",
    "Horizon": "预测或评估周期。",
    "Baseline RankIC": "优化前的排序信息系数。",
    "Optimized RankIC": "优化后的排序信息系数。",
    "Delta": "优化后相对优化前的变化量。",
    "Setting": "参数设置。",
    "Cost": "交易成本假设。",
    "Sharpe": "夏普比率，单位风险对应的收益。",
    "Turnover": "换手率，越高表示交易越频繁。",
    "Criterion": "判断条件。",
    "Test": "测试方法。",
    "Mean": "平均值。",
    "P95": "95 分位值，表示较高但非极端的水平。",
    "P Value": "显著性概率，越低通常越不像随机结果。",
    "Significant": "是否通过显著性判断。",
    "Date": "日期。",
    "Trend": "趋势状态。",
    "Volatility": "波动状态或波动率。",
    "Liquidity": "流动性状态。",
    "Behavior": "行为状态。",
    "Divergence": "背离类型。",
    "Actor": "主导资金类型。",
    "Overlay": "行为叠加状态。",
    "Type": "事件类型。",
    "Probability": "事件概率。",
    "State": "当前状态。",
    "Flow": "资金流冲击概率。",
    "Inst": "机构资金相关指标。",
    "Retail": "散户资金或情绪相关指标。",
    "annual_return": "年化收益率；把区间收益换算成年维度。",
    "sharpe": "夏普比率；越高表示承担同样波动获得的收益越好。",
    "max_drawdown": "最大回撤；越低越好，表示历史最大亏损幅度。",
    "volatility": "收益波动率；越高说明净值波动越大。",
    "win_rate": "胜率；上涨或盈利周期占比。",
    "turnover_rate": "换手率；越高说明组合交易越频繁。",
    "total_transaction_cost": "累计交易成本。",
    "future_leak_rows": "未来函数问题行数；应为 0。",
    "nan_cells": "空值单元格数量；越少越好。",
    "score_std": "评分标准差；太低说明打分区分度不足。",
    "score_min": "最低评分。",
    "score_max": "最高评分。",
    "rank_ic_gt_0_05": "RankIC 是否大于 0.05，用于判断排序信号是否有一定解释力。",
    "positive_sharpe": "夏普是否为正。",
    "stable_oos": "样本外表现是否稳定。",
    "uses_future_return_labels": "是否使用未来收益标签；应为 False。",
    "uses_alpha_model": "是否调用 alpha 模型；异常检测应为 False。",
    "predicts_market_direction": "是否直接预测市场方向；本页异常检测不做方向预测。",
    "purely_observational": "是否纯观察指标，不直接生成买卖指令。",
    "all_scores_bounded_0_1": "所有概率或分数是否限制在 0 到 1。",
    "anomaly_event_frequency": "异常事件出现频率。",
    "high_risk_frequency": "高风险状态出现频率。",
    "recent_30d_mean_anomaly": "最近 30 个交易日平均异常分数。",
}


def _stock_name_lookup(report: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for section in ("stock_coverage", "latest_snapshot"):
        for row in report.get(section, []):
            if not isinstance(row, dict):
                continue
            code = str(row.get("ts_code") or "").strip()
            name = str(row.get("name") or row.get("stock_name") or "").strip()
            if code and name:
                names[code] = name

    for path in report.get("storage", {}).get("by_stock_files", []):
        loaded = _stock_name_from_parquet(str(path))
        if loaded is not None:
            code, name = loaded
            names.setdefault(code, name)
    return names


@lru_cache(maxsize=512)
def _stock_name_from_parquet(path_text: str) -> tuple[str, str] | None:
    path = Path(path_text)
    if not path.exists():
        return None
    try:
        frame = pd.read_parquet(path, columns=["ts_code", "name"])
    except Exception:
        return None
    rows = frame.dropna(subset=["ts_code", "name"]).drop_duplicates(subset=["ts_code"]).head(1)
    if rows.empty:
        return None
    row = rows.iloc[0]
    code = str(row["ts_code"]).strip()
    name = str(row["name"]).strip()
    if not code or not name:
        return None
    return code, name


def _stock_name_for(row: dict[str, Any], stock_names: dict[str, str]) -> str:
    code = str(row.get("ts_code") or "").strip()
    explicit_name = str(row.get("name") or row.get("stock_name") or "").strip()
    return explicit_name or stock_names.get(code, "")


def _stock_code_link(value: Any, stock_name: Any = None) -> str:
    code = str(value or "").strip()
    escaped_code = html.escape(code)
    symbol = _xueqiu_symbol(code)
    if symbol:
        url = f"https://xueqiu.com/S/{symbol}"
        label = html.escape(f"Open {code} on Xueqiu", quote=True)
        code_html = (
            f'<a class="stock-link stock-code-link" href="{url}" target="_blank" '
            f'rel="noopener noreferrer" aria-label="{label}">{escaped_code}</a>'
        )
    else:
        code_html = escaped_code

    name = str(stock_name or "").strip()
    if not code or not name or name == code:
        return code_html

    research_url = _stock_research_url(code)
    escaped_name = html.escape(name)
    label = html.escape(f"Open {name} research page", quote=True)
    name_html = (
        f'<a class="stock-name-link" href="{research_url}" target="_blank" '
        f'rel="noopener noreferrer" aria-label="{label}" title="打开主系统个股研究页">{escaped_name}</a>'
    )
    return f'<span class="stock-identity">{code_html}<span class="stock-name-separator"> </span>{name_html}</span>'


def _stock_research_url(code: str) -> str:
    return f"https://stock.okbbc.com/research?stock={quote(code.strip(), safe='')}"


def _xueqiu_symbol(code: str) -> str | None:
    normalized = code.strip().upper()
    if len(normalized) == 8 and normalized[:2] in {"SH", "SZ", "BJ"} and normalized[2:].isdigit():
        return normalized
    if len(normalized) != 9 or normalized[6] != ".":
        return None
    ticker, exchange = normalized[:6], normalized[7:]
    if exchange not in {"SH", "SZ", "BJ"} or not ticker.isdigit():
        return None
    return f"{exchange}{ticker}"


def _annotate_help(content: str) -> str:
    for label in sorted(HELP_TEXT, key=len, reverse=True):
        escaped_label = html.escape(str(label))
        helped_label = _help_label(label)
        for tag in ("h1", "h2", "th"):
            content = content.replace(f"<{tag}>{escaped_label}</{tag}>", f"<{tag}>{helped_label}</{tag}>")
        content = content.replace(f"<span>{escaped_label}</span>", f"<span>{helped_label}</span>")
        content = content.replace(f"<td>{escaped_label}</td>", f"<td>{helped_label}</td>")
    return content


def _help_label(label: Any) -> str:
    text = str(label)
    escaped_text = html.escape(text)
    help_text = HELP_TEXT.get(text)
    if not help_text:
        return escaped_text
    escaped_help = html.escape(help_text, quote=True)
    return f'<span class="help" title="{escaped_help}" aria-label="{escaped_help}">{escaped_text}</span>'


def _sparkline_svg(rows: list[dict[str, Any]], key: str, color: str) -> str:
    values = [float(row.get(key) or 0.0) for row in rows if row.get(key) is not None]
    if len(values) < 2:
        return "<div class='chart empty'>Not enough data</div>"
    width = 760
    height = 150
    min_value = min(values)
    max_value = max(values)
    span = max(max_value - min_value, 1e-9)
    points = []
    for idx, value in enumerate(values):
        x = idx / max(len(values) - 1, 1) * width
        y = height - ((value - min_value) / span * (height - 20) + 10)
        points.append(f"{x:.2f},{y:.2f}")
    return f"""
    <svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(key)} chart">
      <rect x="0" y="0" width="{width}" height="{height}" rx="8"></rect>
      <polyline points="{' '.join(points)}" fill="none" stroke="{color}" stroke-width="3"></polyline>
    </svg>
    """


def _regime_strip(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<div class='regime-strip empty'>Not enough data</div>"
    colors = {
        "risk_on": "#0f766e",
        "risk_off": "#475569",
        "panic": "#be123c",
        "euphoria": "#b45309",
        "transition": "#64748b",
    }
    cells = []
    for row in rows[-90:]:
        state = str(row.get("behavior_state", "transition"))
        date = html.escape(str(row.get("date", "")))
        cells.append(
            f"<span title='{date} {html.escape(state)}' style='background:{colors.get(state, '#64748b')}'></span>"
        )
    return f"<div class='regime-strip'>{''.join(cells)}</div>"


def _crowding_heatmap(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<div class='regime-strip empty'>Not enough data</div>"
    colors = {
        "low": "#d9f99d",
        "medium": "#fde68a",
        "high": "#fb923c",
        "extreme": "#be123c",
    }
    cells = []
    for row in rows[-90:]:
        level = str(row.get("crowding_level", "low"))
        score = html.escape(_fmt(row.get("positioning_crowdedness")))
        date = html.escape(str(row.get("date", "")))
        cells.append(
            f"<span title='{date} {html.escape(level)} {score}' style='background:{colors.get(level, '#fde68a')}'></span>"
        )
    return f"<div class='regime-strip'>{''.join(cells)}</div>"


def _decomposition_bars(latest: dict[str, Any]) -> str:
    parts = [
        ("Trend", latest.get("trend_component"), "#0f766e"),
        ("Flow", latest.get("flow_component"), "#1d4ed8"),
        ("Volatility", latest.get("volatility_component"), "#be123c"),
        ("Noise", latest.get("noise_component"), "#64748b"),
    ]
    rows = []
    for label, value, color in parts:
        score = float(value or 0.0)
        rows.append(
            f"<div class='bar-row'><span>{html.escape(label)}</span><div><i style='width:{score * 100:.1f}%;background:{color}'></i></div><b>{score:.3f}</b></div>"
        )
    return f"<div class='bars'>{''.join(rows)}</div>"


def _value_heatmap(rows: list[dict[str, Any]], key: str, low_color: str, high_color: str) -> str:
    if not rows:
        return "<div class='regime-strip empty'>Not enough data</div>"
    cells = []
    for row in rows[-90:]:
        value = max(0.0, min(1.0, float(row.get(key) or 0.0)))
        alpha = 0.25 + value * 0.75
        date = html.escape(str(row.get("date", "")))
        cells.append(
            f"<span title='{date} {_fmt(value)}' style='background:{high_color};opacity:{alpha:.2f}'></span>"
        )
    return f"<div class='regime-strip'>{''.join(cells)}</div>"


def _structure_strip(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<div class='regime-strip empty'>Not enough data</div>"
    colors = {
        "balanced_structure": "#0f766e",
        "systemic_stress": "#be123c",
        "fragmented_dispersion": "#b45309",
        "flow_led_accumulation": "#1d4ed8",
        "noisy_transition": "#64748b",
        "trend_flow_aligned": "#7c3aed",
    }
    cells = []
    for row in rows[-90:]:
        state = str(row.get("structure_state", "balanced_structure"))
        date = html.escape(str(row.get("date", "")))
        cells.append(
            f"<span title='{date} {html.escape(state)}' style='background:{colors.get(state, '#64748b')}'></span>"
        )
    return f"<div class='regime-strip'>{''.join(cells)}</div>"


def _anomaly_strip(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<div class='regime-strip empty'>Not enough data</div>"
    colors = {
        "low": "#0f766e",
        "medium": "#b45309",
        "high": "#be123c",
    }
    cells = []
    for row in rows[-90:]:
        risk = str(row.get("systemic_risk_level", "low"))
        state = html.escape(str(row.get("anomaly_state", "")))
        date = html.escape(str(row.get("date", "")))
        cells.append(
            f"<span title='{date} {state}' style='background:{colors.get(risk, '#64748b')}'></span>"
        )
    return f"<div class='regime-strip'>{''.join(cells)}</div>"


def _page(content: str) -> str:
    content = _annotate_help(content)
    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>TenBagger</title>
      <style>
        :root {{
          color-scheme: light;
          --ink: #18202a;
          --muted: #647184;
          --line: #d8dee8;
          --panel: #ffffff;
          --bg: #f4f6f8;
          --accent: #0f766e;
        }}
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0;
          min-height: 100vh;
          font-family: Inter, "Segoe UI", Arial, sans-serif;
          background: var(--bg);
          color: var(--ink);
        }}
        .shell {{
          max-width: 1180px;
          margin: 0 auto;
          padding: 28px;
        }}
        .topbar {{
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 24px;
          margin-bottom: 20px;
        }}
        .topbar-side {{
          display: grid;
          gap: 8px;
          justify-items: end;
        }}
        .model-nav {{
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 12px;
        }}
        .model-nav a,
        .model-nav span {{
          display: inline-flex;
          align-items: center;
          min-height: 34px;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--panel);
          color: var(--ink);
          padding: 7px 11px;
          font-size: 13px;
          font-weight: 700;
          text-decoration: none;
        }}
        .model-nav .active {{
          border-color: #99f6e4;
          background: #ccfbf1;
          color: #115e59;
        }}
        .dataset-badge {{
          display: inline-block;
          border: 1px solid #99f6e4;
          border-radius: 8px;
          background: #ccfbf1;
          color: #115e59;
          padding: 8px 10px;
          font-size: 13px;
          font-weight: 700;
          white-space: nowrap;
        }}
        h1, h2, p {{ margin: 0; }}
        h1 {{ font-size: 30px; line-height: 1.1; }}
        h2 {{ font-size: 18px; margin: 24px 0 10px; }}
        p, .stamp {{ color: var(--muted); }}
        .help {{
          cursor: help;
          text-decoration: underline dotted rgba(15, 118, 110, 0.55);
          text-underline-offset: 3px;
        }}
        .metrics {{
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 12px;
        }}
        .metric {{
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 16px;
          min-height: 88px;
        }}
        .metric span {{
          display: block;
          color: var(--muted);
          font-size: 13px;
          margin-bottom: 8px;
        }}
        .metric strong {{
          display: block;
          font-size: 22px;
          overflow-wrap: anywhere;
        }}
        .grid {{
          display: grid;
          grid-template-columns: 0.8fr 1.2fr;
          gap: 18px;
        }}
        .table-scroll {{
          max-width: 100%;
          overflow: auto;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--panel);
        }}
        .table-scroll table {{
          border: 0;
          border-radius: 0;
        }}
        .coverage-scroll {{
          max-height: 320px;
        }}
        .coverage-scroll thead th {{
          position: sticky;
          top: 0;
          z-index: 1;
        }}
        table {{
          width: 100%;
          border-collapse: collapse;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          overflow: hidden;
        }}
        th, td {{
          text-align: left;
          padding: 10px 12px;
          border-bottom: 1px solid var(--line);
          font-size: 13px;
          white-space: nowrap;
        }}
        th {{
          color: var(--muted);
          font-weight: 600;
          background: #eef2f5;
        }}
        tr:last-child td {{ border-bottom: 0; }}
        .stock-identity {{
          display: inline-flex;
          align-items: baseline;
          gap: 8px;
          white-space: nowrap;
        }}
        .stock-link {{
          display: inline-block;
          color: var(--accent);
          font-size: 13px;
          font-weight: 600;
          text-decoration: none;
        }}
        .stock-name-link {{
          color: #1d4ed8;
          font-size: 12px;
          font-weight: 600;
          text-decoration: none;
        }}
        .stock-link:hover,
        .stock-name-link:hover {{
          text-decoration: underline;
        }}
        .empty {{
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 24px;
        }}
        .chart {{
          display: block;
          width: 100%;
          height: 150px;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
        }}
        .chart rect {{
          fill: #ffffff;
        }}
        .regime-strip {{
          display: grid;
          grid-template-columns: repeat(90, minmax(4px, 1fr));
          gap: 2px;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 12px;
        }}
        .regime-strip span {{
          display: block;
          min-height: 26px;
          border-radius: 3px;
        }}
        .bars {{
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 14px;
        }}
        .bar-row {{
          display: grid;
          grid-template-columns: 110px 1fr 64px;
          align-items: center;
          gap: 10px;
          margin: 10px 0;
          font-size: 13px;
        }}
        .bar-row div {{
          height: 14px;
          background: #e5e7eb;
          border-radius: 999px;
          overflow: hidden;
        }}
        .bar-row i {{
          display: block;
          height: 100%;
        }}
        @media (max-width: 860px) {{
          .shell {{ padding: 18px; }}
          .topbar {{ display: block; }}
          .topbar-side {{ justify-items: start; margin-top: 10px; }}
          .dataset-badge {{ white-space: normal; }}
          .stamp {{ margin-top: 8px; }}
          .metrics, .grid {{ grid-template-columns: 1fr; }}
          table {{ display: block; overflow-x: auto; }}
        }}
      </style>
    </head>
    <body>
      <div data-myinvest-header></div>
      {content}
      <div data-myinvest-footer></div>
      <script
        src="https://invest.okbbc.com/header.js"
        data-target="[data-myinvest-header]"
        data-api="https://invest.okbbc.com/api/header"
        defer
      ></script>
      <script
        src="https://invest.okbbc.com/footer.js"
        data-target="[data-myinvest-footer]"
        data-api="https://invest.okbbc.com/api/footer"
        defer
      ></script>
    </body>
    </html>
    """
