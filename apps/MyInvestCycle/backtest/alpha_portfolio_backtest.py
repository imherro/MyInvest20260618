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
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "alpha_portfolio_backtest.json"
TRANSACTION_COST = 0.001
BENCHMARKS = ("510300.SH", "510500.SH")


def _price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return pd.DataFrame(columns=["trade_date", "close"])
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    return result.dropna(subset=["trade_date", "close"])[["trade_date", "close"]].sort_values("trade_date").reset_index(drop=True)


def _return_map(frame: pd.DataFrame) -> dict[str, float]:
    clean = _price_frame(frame)
    clean["return"] = clean["close"].pct_change().fillna(0.0)
    return {str(row.trade_date): float(row.return_) for row in clean.rename(columns={"return": "return_"}).itertuples()}


def _calendar(benchmark: pd.DataFrame, start: str, end: str) -> list[str]:
    clean = _price_frame(benchmark)
    return [str(date) for date in clean["trade_date"] if start <= str(date) <= end]


def _next_date(calendar: list[str], date: str) -> str | None:
    for item in calendar:
        if item > date:
            return item
    return None


def _turnover(old: set[str], new: set[str]) -> float:
    if not old:
        return 1.0 if new else 0.0
    if not new:
        return 1.0
    return 1.0 - len(old & new) / len(new)


def _portfolio_daily_return(codes: set[str], returns_by_code: Mapping[str, Mapping[str, float]], date: str) -> float:
    if not codes:
        return 0.0
    values = [returns_by_code.get(code, {}).get(date, 0.0) for code in codes]
    return sum(values) / len(values) if values else 0.0


def _metrics(curve: list[dict[str, object]], turnovers: list[float]) -> dict[str, object]:
    if len(curve) < 2:
        return {}
    equity = pd.Series([float(row["equity"]) for row in curve])
    daily = equity.pct_change().fillna(0.0)
    total = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = max((len(curve) - 1) / 252.0, 1 / 252.0)
    annualized = (float(equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years)) - 1.0
    volatility = float(daily.std() * math.sqrt(252.0))
    sharpe = annualized / volatility if volatility else None
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return {
        "total_return": round(total, 6),
        "annualized_return": round(annualized, 6),
        "volatility": round(volatility, 6),
        "max_drawdown": round(float(drawdown.min()), 6),
        "sharpe": None if sharpe is None else round(float(sharpe), 6),
        "rebalance_count": len(turnovers),
        "avg_turnover": None if not turnovers else round(sum(turnovers) / len(turnovers), 6),
        "avg_holding_days": None if not turnovers else round((len(curve) - 1) / len(turnovers), 4),
    }


def _theme_map() -> dict[str, str]:
    return {asset.code: (asset.theme or asset.category) for asset in read_asset_registry()}


def _theme_concentration(plan_rows: list[Mapping[str, object]]) -> dict[str, object]:
    themes = _theme_map()
    max_values: list[float] = []
    latest: dict[str, float] = {}
    for row in plan_rows:
        codes = list(row.get("selected_codes") or [])
        if not codes:
            continue
        counts: dict[str, int] = defaultdict(int)
        for code in codes:
            counts[themes.get(str(code), str(code))] += 1
        shares = {theme: count / len(codes) for theme, count in counts.items()}
        max_values.append(max(shares.values()))
        latest = shares
    return {
        "average_max_theme_share": None if not max_values else round(sum(max_values) / len(max_values), 6),
        "latest_theme_shares": {key: round(value, 6) for key, value in sorted(latest.items())},
        "theme_source": "asset_registry.theme",
    }


def _run_strategy(
    *,
    plan_rows: list[Mapping[str, object]],
    histories: Mapping[str, pd.DataFrame],
    benchmark: pd.DataFrame,
    start: str,
    end: str,
    model_label: str,
    top_n: int,
    transaction_cost: float,
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
    for index, date in enumerate(calendar):
        if started and index > 0:
            equity *= 1.0 + _portfolio_daily_return(holdings, returns_by_code, date)
        if date in entry_by_date:
            row = entry_by_date[date]
            new_holdings = set(str(code) for code in row.get("selected_codes") or [])
            turn = _turnover(holdings, new_holdings)
            equity *= 1.0 - transaction_cost * turn
            turnovers.append(turn)
            holdings = new_holdings
            active_rows.append(row)
            started = True
        if started:
            curve.append({"date": date, "equity": round(equity, 6), "holding_count": len(holdings)})
    return {
        "model_label": model_label,
        "top_n": top_n,
        "metrics": _metrics(curve, turnovers),
        "theme_concentration": _theme_concentration(active_rows),
        "equity_curve": curve,
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


def _benchmark_curve(frame: pd.DataFrame, start: str, end: str) -> dict[str, object]:
    clean = _price_frame(frame)
    clean = clean[(clean["trade_date"] >= start) & (clean["trade_date"] <= end)].reset_index(drop=True)
    if clean.empty:
        return {"metrics": {}, "equity_curve": []}
    first = float(clean["close"].iloc[0])
    curve = [
        {"date": str(row.trade_date), "equity": round(float(row.close) / first, 6)}
        for row in clean.itertuples()
    ]
    return {"metrics": _metrics(curve, []), "equity_curve": curve}


def build_alpha_portfolio_backtest(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    step_sessions: int = 20,
    transaction_cost: float = TRANSACTION_COST,
) -> dict[str, object]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    mappings = [mapping for mapping in read_asset_proxy_registry(registry_path) if mapping.enabled]
    plan = build_alpha_portfolio_plan(
        start_date=start,
        end_date=end,
        registry_path=registry_path,
        step_sessions=step_sessions,
    )
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
    plan_rows = list(plan["plan"])
    benchmark_calendar = _calendar(benchmark, start, end)
    entry_dates = [
        entry for entry in (_next_date(benchmark_calendar, str(row["signal_date"])) for row in plan_rows)
        if entry is not None
    ]
    active_start = min(entry_dates) if entry_dates else start
    strategy_results = {
        "research_proxy": {},
        "tradable_etf": {},
    }
    for mode, histories in (("research_proxy", research_histories), ("tradable_etf", tradable_histories)):
        for model_label in ("opportunity_score", "router_selected_model"):
            for top_n in TOP_N_VALUES:
                key = f"{model_label}_top{top_n}"
                strategy_results[mode][key] = _run_strategy(
                    plan_rows=plan_rows,
                    histories=histories,
                    benchmark=benchmark,
                    start=start,
                    end=end,
                    model_label=model_label,
                    top_n=top_n,
                    transaction_cost=transaction_cost,
                )
    benchmarks = {
        code: _benchmark_curve(read_benchmark_cache(code, start, end), active_start, end)
        for code in BENCHMARKS
    }
    return {
        "metadata": {
            "engine": "V3.4.2 Alpha Portfolio Simulation & Risk Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start, "end": end},
            "step_sessions": step_sessions,
            "transaction_cost": transaction_cost,
            "entry_rule": "T+1 close",
            "active_start": active_start,
            "weighting": "fixed equal weight inside Top-N simulation",
        },
        "plan_summary": plan["summary"],
        "strategies": strategy_results,
        "benchmarks": benchmarks,
        "constraints": {
            "simulation_only": True,
            "equal_weight": True,
            "t_plus_1_entry": True,
            "transaction_cost_explicit": True,
            "no_dynamic_weight_optimization": True,
            "no_parameter_search": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "proxy_return_and_etf_return_separated": True,
        },
    }


def write_alpha_portfolio_backtest(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
