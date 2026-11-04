from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

from asset_opportunity.alpha_portfolio_engine import build_alpha_portfolio_plan
from asset_opportunity.alpha_style_attribution import dominant_style, style_exposure_for_codes
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH
from asset_opportunity.opportunity_score_engine import DEFAULT_BENCHMARK
from backtest.alpha_portfolio_backtest import _calendar, _next_date
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date


STYLE_BENCHMARKS = (
    {"code": "159915.SZ", "name": "创业板ETF", "style": "growth_technology"},
    {"code": "588000.SH", "name": "科创50ETF", "style": "growth_technology"},
    {"code": "512480.SH", "name": "半导体ETF", "style": "growth_technology"},
    {"code": "510880.SH", "name": "红利ETF", "style": "dividend_defensive"},
    {"code": "510300.SH", "name": "沪深300ETF", "style": "value_large"},
    {"code": "510500.SH", "name": "中证500ETF", "style": "mid_small"},
)


DEFAULT_ATTRIBUTION_PERIODS = (
    {"label": "2020-2021", "start": "20200101", "end": "20211231"},
    {"label": "2022", "start": "20220101", "end": "20221231"},
    {"label": "2023", "start": "20230101", "end": "20231231"},
    {"label": "2024-2026", "start": "20240101", "end": "20260708"},
)


def _average_exposure(exposures: Iterable[Mapping[str, float]]) -> dict[str, float]:
    rows = list(exposures)
    if not rows:
        return {}
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        for style, share in row.items():
            totals[style] += float(share)
    return {
        style: round(value / len(rows), 6)
        for style, value in sorted(totals.items())
    }


def _entry_rows(plan_rows: list[Mapping[str, object]], calendar: list[str]) -> dict[str, Mapping[str, object]]:
    entries: dict[str, Mapping[str, object]] = {}
    for row in plan_rows:
        entry = _next_date(calendar, str(row["signal_date"]))
        if entry is not None:
            entries[entry] = row
    return entries


def build_style_exposure_analysis(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    step_sessions: int = 60,
    model_label: str = "router_selected_model",
    top_n: int = 3,
    periods: Iterable[Mapping[str, str]] = DEFAULT_ATTRIBUTION_PERIODS,
) -> dict[str, object]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    plan = build_alpha_portfolio_plan(
        start_date=start,
        end_date=end,
        registry_path=registry_path,
        step_sessions=step_sessions,
    )
    benchmark = read_benchmark_cache(DEFAULT_BENCHMARK, start, end)
    calendar = _calendar(benchmark, start, end)
    rows = [
        row for row in plan["plan"]
        if row.get("model_label") == model_label and int(row.get("top_n") or 0) == top_n
    ]
    entry_by_date = _entry_rows(rows, calendar)

    holdings: list[str] = []
    daily_exposures: list[dict[str, object]] = []
    rebalance_counter: Counter[str] = Counter()
    for date in calendar:
        if date in entry_by_date:
            holdings = [str(code) for code in entry_by_date[date].get("selected_codes") or []]
            rebalance_counter.update(holdings)
        if holdings:
            exposure = style_exposure_for_codes(holdings)
            daily_exposures.append(
                {
                    "date": date,
                    "codes": holdings,
                    "exposure": exposure,
                    "dominant": dominant_style(exposure),
                }
            )

    period_results: list[dict[str, object]] = []
    for period in periods:
        period_start = normalize_trade_date(period["start"])
        period_end = normalize_trade_date(period["end"])
        rows_in_period = [
            row for row in daily_exposures
            if period_start <= str(row["date"]) <= period_end
        ]
        exposure = _average_exposure(row["exposure"] for row in rows_in_period)
        period_results.append(
            {
                "label": period["label"],
                "window": {"start": period_start, "end": period_end},
                "observations": len(rows_in_period),
                "average_style_exposure": exposure,
                "dominant_style": dominant_style(exposure),
            }
        )

    latest = daily_exposures[-1] if daily_exposures else {}
    return {
        "metadata": {
            "engine": "V3.4.4 Style Exposure Analysis",
            "window": {"start": start, "end": end},
            "model_label": model_label,
            "top_n": top_n,
            "rebalance_step": step_sessions,
        },
        "style_benchmarks": list(STYLE_BENCHMARKS),
        "periods": period_results,
        "latest_exposure": latest,
        "selected_code_counts": dict(sorted(rebalance_counter.items())),
        "constraints": {
            "analysis_only": True,
            "model_unchanged": True,
            "router_unchanged": True,
            "top_n_unchanged": True,
            "rebalance_step_unchanged": True,
            "no_theme_cap": True,
            "no_allocation": True,
            "no_trade_signal": True,
        },
    }
