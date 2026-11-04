from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Mapping

import pandas as pd

from asset_opportunity.alpha_model_portfolio import TOP_N_VALUES
from asset_opportunity.alpha_portfolio_engine import build_alpha_portfolio_plan
from asset_opportunity.asset_loader import load_asset_history
from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from asset_opportunity.asset_registry import read_asset_registry
from asset_opportunity.opportunity_score_engine import DEFAULT_BENCHMARK
from asset_opportunity.portfolio_risk_control import (
    RiskControlScenario,
    attach_concentration_level,
    default_risk_control_scenarios,
)
from backtest.alpha_portfolio_backtest import (
    BENCHMARKS,
    _benchmark_curve,
    _calendar,
    _next_date,
    _portfolio_daily_return,
    _return_map,
    _turnover,
)
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "alpha_portfolio_risk_validation.json"


def _risk_metrics(curve: list[dict[str, object]], turnovers: list[float]) -> dict[str, object]:
    if len(curve) < 2:
        return {}
    equity = pd.Series([float(row["equity"]) for row in curve])
    daily = equity.pct_change().fillna(0.0)
    total = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = max((len(curve) - 1) / 252.0, 1 / 252.0)
    cagr = (float(equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years)) - 1.0
    volatility = float(daily.std() * math.sqrt(252.0))
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_drawdown = float(drawdown.min())
    sharpe = cagr / volatility if volatility else None
    calmar = cagr / abs(max_drawdown) if max_drawdown else None
    return {
        "total_return": round(total, 6),
        "annualized_return": round(cagr, 6),
        "cagr": round(cagr, 6),
        "volatility": round(volatility, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe": None if sharpe is None else round(float(sharpe), 6),
        "calmar": None if calmar is None else round(float(calmar), 6),
        "rebalance_count": len(turnovers),
        "total_turnover": round(sum(turnovers), 6),
        "avg_turnover": None if not turnovers else round(sum(turnovers) / len(turnovers), 6),
        "avg_holding_days": None if not turnovers else round((len(curve) - 1) / len(turnovers), 4),
    }


def _risk_theme_for_asset(tags: set[str], raw_theme: str, category: str) -> str:
    if tags & {"technology", "growth"}:
        return "growth_technology"
    if "new_energy" in tags:
        return "new_energy"
    if "financial" in tags:
        return "financial"
    if "consumer" in tags:
        return "consumer"
    if "healthcare" in tags:
        return "healthcare"
    if "defense" in tags:
        return "defense"
    if tags & {"dividend", "low_vol"}:
        return "dividend_low_vol"
    if category == "broad":
        return "broad_market"
    return raw_theme or category


def _theme_maps() -> tuple[dict[str, str], dict[str, str]]:
    raw: dict[str, str] = {}
    risk: dict[str, str] = {}
    for asset in read_asset_registry():
        raw_theme = asset.theme or asset.category
        raw[asset.code] = raw_theme
        risk[asset.code] = _risk_theme_for_asset(set(asset.tags), raw_theme, asset.category)
    return raw, risk


def _concentration_by_map(
    plan_rows: list[Mapping[str, object]],
    theme_map: Mapping[str, str],
    *,
    theme_source: str,
) -> dict[str, object]:
    max_values: list[float] = []
    latest: dict[str, float] = {}
    for row in plan_rows:
        codes = list(row.get("selected_codes") or [])
        if not codes:
            continue
        counts: dict[str, int] = defaultdict(int)
        for code in codes:
            counts[theme_map.get(str(code), str(code))] += 1
        shares = {theme: count / len(codes) for theme, count in counts.items()}
        max_values.append(max(shares.values()))
        latest = shares
    return {
        "average_max_theme_share": None if not max_values else round(sum(max_values) / len(max_values), 6),
        "latest_theme_shares": {key: round(value, 6) for key, value in sorted(latest.items())},
        "theme_source": theme_source,
    }


def _theme_monitor(plan_rows: list[Mapping[str, object]]) -> dict[str, object]:
    raw_map, risk_map = _theme_maps()
    raw = attach_concentration_level(
        _concentration_by_map(plan_rows, raw_map, theme_source="asset_registry.theme")
    )
    risk = attach_concentration_level(
        _concentration_by_map(plan_rows, risk_map, theme_source="asset_registry.tags collapsed into risk themes")
    )
    return {
        **risk,
        "raw_theme_monitor": raw,
        "risk_theme_method": "technology/growth style tags are collapsed to avoid false diversification.",
    }


def _run_risk_strategy(
    *,
    plan_rows: list[Mapping[str, object]],
    histories: Mapping[str, pd.DataFrame],
    benchmark: pd.DataFrame,
    start: str,
    end: str,
    model_label: str,
    top_n: int,
    scenario: RiskControlScenario,
) -> dict[str, object]:
    calendar = _calendar(benchmark, start, end)
    returns_by_code = {code: _return_map(frame) for code, frame in histories.items()}
    rows = [
        row for row in plan_rows
        if row.get("model_label") == model_label and int(row.get("top_n") or 0) == top_n
    ]
    entry_by_date: dict[str, Mapping[str, object]] = {}
    for row in rows:
        entry = _next_date(calendar, str(row["signal_date"]))
        if entry is not None:
            entry_by_date[entry] = row

    equity = 1.0
    holdings: set[str] = set()
    curve: list[dict[str, object]] = []
    turnovers: list[float] = []
    active_rows: list[Mapping[str, object]] = []
    started = False
    skipped_min_holding = 0
    last_rebalance_index: int | None = None

    for index, date in enumerate(calendar):
        if started and index > 0:
            equity *= 1.0 + _portfolio_daily_return(holdings, returns_by_code, date)
        if date in entry_by_date:
            if (
                last_rebalance_index is not None
                and scenario.minimum_holding_days > 0
                and index - last_rebalance_index < scenario.minimum_holding_days
            ):
                skipped_min_holding += 1
            else:
                row = entry_by_date[date]
                new_holdings = set(str(code) for code in row.get("selected_codes") or [])
                turn = _turnover(holdings, new_holdings)
                equity *= 1.0 - scenario.transaction_cost * turn
                turnovers.append(turn)
                holdings = new_holdings
                active_rows.append(row)
                started = True
                last_rebalance_index = index
        if started:
            curve.append({"date": date, "equity": round(equity, 6), "holding_count": len(holdings)})

    return {
        "model_label": model_label,
        "top_n": top_n,
        "metrics": _risk_metrics(curve, turnovers),
        "theme_concentration": _theme_monitor(active_rows),
        "skipped_by_minimum_holding": skipped_min_holding,
        "equity_curve_tail": curve[-5:],
        "sample_rebalances": [
            {
                "signal_date": row["signal_date"],
                "regime": row["regime"],
                "selected_model": row["selected_model"],
                "selected_assets": row["selected_assets"],
            }
            for row in active_rows[-5:]
        ],
    }


def _benchmark_metrics(frame: pd.DataFrame, start: str, end: str) -> dict[str, object]:
    result = _benchmark_curve(frame, start, end)
    curve = list(result.get("equity_curve") or [])
    return {**_risk_metrics(curve, []), "equity_curve_tail": curve[-5:]}


def _scenario_summary(payload: dict[str, object]) -> dict[str, object]:
    scenarios = payload.get("scenarios") or {}
    rebalance_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    min_hold_rows: list[dict[str, object]] = []
    for label, scenario in scenarios.items():
        if not isinstance(scenario, Mapping):
            continue
        config = scenario.get("config") or {}
        strategies = scenario.get("strategies") or {}
        tradable = (strategies.get("tradable_etf") or {}).get("router_selected_model_top3") or {}
        metrics = tradable.get("metrics") or {}
        row = {
            "scenario": label,
            "rebalance_step": config.get("rebalance_step"),
            "transaction_cost": config.get("transaction_cost"),
            "minimum_holding_days": config.get("minimum_holding_days"),
            "cagr": metrics.get("cagr"),
            "max_drawdown": metrics.get("max_drawdown"),
            "sharpe": metrics.get("sharpe"),
            "calmar": metrics.get("calmar"),
            "avg_turnover": metrics.get("avg_turnover"),
            "rebalance_count": metrics.get("rebalance_count"),
        }
        if config.get("transaction_cost") == 0.001 and config.get("minimum_holding_days") == 20:
            rebalance_rows.append(row)
        if config.get("rebalance_step") == 20 and config.get("minimum_holding_days") == 20:
            cost_rows.append(row)
        if config.get("rebalance_step") == 20 and config.get("transaction_cost") == 0.001:
            min_hold_rows.append(row)
    return {
        "primary_series": "tradable_etf.router_selected_model_top3",
        "rebalance_sensitivity": sorted(rebalance_rows, key=lambda item: int(item["rebalance_step"] or 0)),
        "cost_sensitivity": sorted(cost_rows, key=lambda item: float(item["transaction_cost"] or 0.0)),
        "minimum_holding_sensitivity": sorted(min_hold_rows, key=lambda item: int(item["minimum_holding_days"] or 0)),
        "selection_policy": "No best scenario is selected; tables are fixed risk-control sensitivity checks.",
    }


def build_alpha_portfolio_risk_validation(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    scenarios: list[RiskControlScenario] | None = None,
) -> dict[str, object]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    scenario_list = list(scenarios or default_risk_control_scenarios())
    mappings = [mapping for mapping in read_asset_proxy_registry(registry_path) if mapping.enabled]
    research_histories = {
        mapping.asset_code: load_research_proxy_history(mapping, start, end, cache_only=True)
        for mapping in mappings
    }
    tradable_histories = {
        mapping.asset_code: load_asset_history(
            {
                "code": mapping.asset_code,
                "name": mapping.asset_name,
                "type": mapping.asset_type,
                "category": mapping.asset_category,
                "source": "Tushare fund_daily",
                "benchmark": DEFAULT_BENCHMARK,
                "enabled": mapping.enabled,
            },
            start,
            end,
            cache_only=True,
        )
        for mapping in mappings
    }
    benchmark = read_benchmark_cache(DEFAULT_BENCHMARK, start, end)

    plan_by_step: dict[int, dict[str, object]] = {}
    rows_by_step: dict[int, list[Mapping[str, object]]] = {}
    active_start_by_step: dict[int, str] = {}
    benchmark_calendar = _calendar(benchmark, start, end)
    for step in sorted({scenario.rebalance_step for scenario in scenario_list}):
        plan = build_alpha_portfolio_plan(
            start_date=start,
            end_date=end,
            registry_path=registry_path,
            step_sessions=step,
        )
        rows = list(plan["plan"])
        entries = [
            entry for entry in (_next_date(benchmark_calendar, str(row["signal_date"])) for row in rows)
            if entry is not None
        ]
        plan_by_step[step] = plan
        rows_by_step[step] = rows
        active_start_by_step[step] = min(entries) if entries else start

    scenario_results: dict[str, object] = {}
    for scenario in scenario_list:
        plan_rows = rows_by_step[scenario.rebalance_step]
        strategy_results: dict[str, object] = {"research_proxy": {}, "tradable_etf": {}}
        for mode, histories in (("research_proxy", research_histories), ("tradable_etf", tradable_histories)):
            for model_label in ("opportunity_score", "router_selected_model"):
                for top_n in TOP_N_VALUES:
                    key = f"{model_label}_top{top_n}"
                    strategy_results[mode][key] = _run_risk_strategy(
                        plan_rows=plan_rows,
                        histories=histories,
                        benchmark=benchmark,
                        start=start,
                        end=end,
                        model_label=model_label,
                        top_n=top_n,
                        scenario=scenario,
                    )
        active_start = active_start_by_step[scenario.rebalance_step]
        scenario_results[scenario.label] = {
            "config": scenario.to_dict(),
            "plan_summary": plan_by_step[scenario.rebalance_step]["summary"],
            "active_start": active_start,
            "strategies": strategy_results,
            "benchmarks": {
                code: _benchmark_metrics(read_benchmark_cache(code, start, end), active_start, end)
                for code in BENCHMARKS
            },
        }

    payload = {
        "metadata": {
            "engine": "V3.4.3 Alpha Portfolio Risk Control Layer",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start, "end": end},
            "scenario_count": len(scenario_results),
            "entry_rule": "T+1 close",
            "weighting": "fixed equal weight inside Top-N simulation",
        },
        "scenario_design": {
            "rebalance_steps": sorted({scenario.rebalance_step for scenario in scenario_list}),
            "transaction_costs": sorted({scenario.transaction_cost for scenario in scenario_list}),
            "minimum_holding_days": sorted({scenario.minimum_holding_days for scenario in scenario_list}),
            "theme_control": "monitor only; no automatic filtering",
        },
        "scenarios": scenario_results,
        "constraints": {
            "simulation_only": True,
            "model_formulas_frozen": True,
            "equal_weight": True,
            "t_plus_1_entry": True,
            "cost_transparent": True,
            "turnover_transparent": True,
            "theme_concentration_monitor_only": True,
            "no_dynamic_weight": True,
            "no_parameter_optimization": True,
            "no_best_parameter_selection": True,
            "no_etf_auto_allocation": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "proxy_return_and_etf_return_separated": True,
        },
    }
    payload["summary"] = _scenario_summary(payload)
    return payload


def write_alpha_portfolio_risk_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
