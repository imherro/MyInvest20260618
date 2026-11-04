from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from asset_opportunity.asset_loader import load_asset_history
from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from asset_opportunity.factor_attribution import spearman_ic
from asset_opportunity.opportunity_score_engine import DEFAULT_BENCHMARK
from asset_opportunity.opportunity_validation import _forward_return, _score_rows_for_date, _validation_dates
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date
from style_allocation.style_schema import STYLE_IDS, style_for_asset_code
from style_allocation.style_validation import (
    VALIDATION_STATES,
    baseline_top_codes,
    build_historical_style_preference,
    structural_row_for_date,
    style_pool_codes,
)


DEFAULT_OUTPUT_PATH = DATA_DIR / "style_validation.json"
DEFAULT_HORIZONS = (20, 60)
TOP_N = 3


def _read_structural_rows(path: str | Path = DATA_DIR / "structural_hazard_dataset.json") -> list[dict[str, object]]:
    source = Path(path)
    if not source.exists():
        return []
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    rows = [row for row in payload if isinstance(row, Mapping)]
    return sorted((dict(row) for row in rows), key=lambda item: str(item.get("date")))


def _mean(values: Iterable[float]) -> float | None:
    clean = [float(value) for value in values if pd.notna(value)]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _average_forward_return(
    histories: Mapping[str, pd.DataFrame],
    codes: list[str],
    date_text: str,
    horizon: int,
) -> float | None:
    returns: list[float] = []
    for code in codes:
        frame = histories.get(code)
        if frame is None:
            continue
        future = _forward_return(frame, date_text, horizon)
        if future is not None:
            returns.append(float(future))
    return _mean(returns)


def _style_forward_returns(
    histories: Mapping[str, pd.DataFrame],
    score_rows: list[Mapping[str, object]],
    date_text: str,
    horizon: int,
    top_n: int,
) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for style_id in STYLE_IDS:
        codes = style_pool_codes(score_rows, style_id, top_n=top_n)
        result[style_id] = _average_forward_return(histories, codes, date_text, horizon)
    return result


def _style_ic(preference: Mapping[str, object], style_returns: Mapping[str, float | None]) -> float | None:
    scores = preference.get("style_scores") or {}
    rows = [
        {"style": style_id, "score": scores.get(style_id), "future_return": style_returns.get(style_id)}
        for style_id in STYLE_IDS
        if style_returns.get(style_id) is not None
    ]
    return spearman_ic(rows, "score")


def _summarize_observations(rows: list[Mapping[str, object]]) -> dict[str, object]:
    spreads = [float(row["relative_to_baseline"]) for row in rows if row.get("relative_to_baseline") is not None]
    baseline_returns = [float(row["baseline_return"]) for row in rows if row.get("baseline_return") is not None]
    style_returns = [float(row["style_aware_return"]) for row in rows if row.get("style_aware_return") is not None]
    ics = [float(row["style_ic"]) for row in rows if row.get("style_ic") is not None]
    hits = [
        1.0 if float(row["style_aware_return"]) > float(row["baseline_return"]) else 0.0
        for row in rows
        if row.get("style_aware_return") is not None and row.get("baseline_return") is not None
    ]
    return {
        "date_count": len({str(row.get("date")) for row in rows}),
        "observation_count": len(rows),
        "baseline_return": None if not baseline_returns else round(sum(baseline_returns) / len(baseline_returns), 6),
        "style_aware_return": None if not style_returns else round(sum(style_returns) / len(style_returns), 6),
        "spread": None if not spreads else round(sum(spreads) / len(spreads), 6),
        "hit_rate": None if not hits else round(sum(hits) / len(hits), 6),
        "style_ic": None if not ics else round(sum(ics) / len(ics), 6),
        "positive_ic_rate": None if not ics else round(sum(1 for value in ics if value > 0) / len(ics), 6),
    }


def _group_summary(
    rows: list[Mapping[str, object]],
    key: str,
    categories: Iterable[str] | None = None,
) -> dict[str, object]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "unknown")].append(row)
    if categories is not None:
        for category in categories:
            grouped.setdefault(str(category), [])
    return {group: _summarize_observations(items) for group, items in sorted(grouped.items())}


def _observations_for_mode(
    *,
    mode: str,
    dates: list[str],
    scored_rows_by_date: Mapping[str, list[Mapping[str, object]]],
    return_histories: Mapping[str, pd.DataFrame],
    structural_rows: list[Mapping[str, object]],
    horizons: tuple[int, ...],
    top_n: int,
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {f"{horizon}d": [] for horizon in horizons}
    for date_text in dates:
        score_rows = scored_rows_by_date.get(date_text) or []
        structural_row = structural_row_for_date(structural_rows, date_text)
        preference = build_historical_style_preference(
            date_text=date_text,
            structural_row=structural_row,
            score_rows=score_rows,
        )
        baseline_codes = baseline_top_codes(score_rows, top_n=top_n)
        style_codes = style_pool_codes(score_rows, str(preference["dominant_style"]), top_n=top_n)
        for horizon in horizons:
            baseline_return = _average_forward_return(return_histories, baseline_codes, date_text, horizon)
            style_aware_return = _average_forward_return(return_histories, style_codes, date_text, horizon)
            if baseline_return is None or style_aware_return is None:
                continue
            style_returns = _style_forward_returns(return_histories, score_rows, date_text, horizon, top_n)
            style_ic = _style_ic(preference, style_returns)
            result[f"{horizon}d"].append(
                {
                    "mode": mode,
                    "date": date_text,
                    "validation_state": preference["validation_state"],
                    "dominant_style": preference["dominant_style"],
                    "baseline_codes": baseline_codes,
                    "style_aware_codes": style_codes,
                    "baseline_return": round(float(baseline_return), 6),
                    "style_aware_return": round(float(style_aware_return), 6),
                    "relative_to_baseline": round(float(style_aware_return - baseline_return), 6),
                    "hit": bool(style_aware_return > baseline_return),
                    "style_ic": style_ic,
                    "style_scores": preference["style_scores"],
                    "style_forward_returns": {
                        style_id: None if value is None else round(float(value), 6)
                        for style_id, value in style_returns.items()
                    },
                }
            )
    return result


def _summaries(observations: Mapping[str, list[Mapping[str, object]]]) -> dict[str, object]:
    return {
        horizon: {
            "overall": _summarize_observations(rows),
            "by_state": _group_summary(rows, "validation_state", VALIDATION_STATES),
            "by_dominant_style": _group_summary(rows, "dominant_style", STYLE_IDS),
        }
        for horizon, rows in observations.items()
    }


def _edge_read(tradable_summary: Mapping[str, object]) -> dict[str, object]:
    h20 = ((tradable_summary.get("20d") or {}).get("overall") or {})
    h60 = ((tradable_summary.get("60d") or {}).get("overall") or {})
    structural_20 = (((tradable_summary.get("20d") or {}).get("by_state") or {}).get("STRUCTURAL_BULL") or {})
    structural_60 = (((tradable_summary.get("60d") or {}).get("by_state") or {}).get("STRUCTURAL_BULL") or {})
    spread_20 = h20.get("spread")
    spread_60 = h60.get("spread")
    hit_20 = h20.get("hit_rate")
    hit_60 = h60.get("hit_rate")
    if (
        spread_20 is not None
        and spread_60 is not None
        and float(spread_20) > 0
        and float(spread_60) > 0
        and hit_20 is not None
        and hit_60 is not None
        and float(hit_20) > 0.5
        and float(hit_60) > 0.5
    ):
        status = "positive"
    elif spread_20 is not None and float(spread_20) > 0 and (spread_60 is None or float(spread_60) <= 0):
        status = "short_horizon_only"
    else:
        status = "weak_or_inconclusive"
    return {
        "style_preference_edge_status": status,
        "tradable_20d_spread": spread_20,
        "tradable_20d_hit_rate": hit_20,
        "tradable_60d_spread": spread_60,
        "tradable_60d_hit_rate": hit_60,
        "structural_bull_20d_spread": structural_20.get("spread"),
        "structural_bull_60d_spread": structural_60.get("spread"),
        "interpretation": (
            "Style preference shows a short-horizon and structural-bull edge if 20d spread is positive, "
            "but it should not become allocation until 60d spread, hit rate, and IC are robust across states."
        ),
    }


def build_style_validation(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    step_sessions: int = 20,
    min_score_sessions: int = 260,
    top_n: int = TOP_N,
) -> dict[str, object]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
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
    dates = _validation_dates(
        benchmark,
        research_histories,
        start_date=start,
        end_date=end,
        step_sessions=step_sessions,
        min_score_sessions=min_score_sessions,
    )
    scored_rows_by_date = {
        date_text: _score_rows_for_date(mappings, research_histories, benchmark, date_text)
        for date_text in dates
    }
    structural_rows = _read_structural_rows()
    research_observations = _observations_for_mode(
        mode="research_proxy_return",
        dates=dates,
        scored_rows_by_date=scored_rows_by_date,
        return_histories=research_histories,
        structural_rows=structural_rows,
        horizons=horizons,
        top_n=top_n,
    )
    tradable_observations = _observations_for_mode(
        mode="tradable_etf_return",
        dates=dates,
        scored_rows_by_date=scored_rows_by_date,
        return_histories=tradable_histories,
        structural_rows=structural_rows,
        horizons=horizons,
        top_n=top_n,
    )
    sample_preferences = []
    for date_text in dates[-5:]:
        preference = build_historical_style_preference(
            date_text=date_text,
            structural_row=structural_row_for_date(structural_rows, date_text),
            score_rows=scored_rows_by_date[date_text],
        )
        sample_preferences.append(
            {
                "date": date_text,
                "validation_state": preference["validation_state"],
                "dominant_style": preference["dominant_style"],
                "style_scores": preference["style_scores"],
            }
        )

    research_summary = _summaries(research_observations)
    tradable_summary = _summaries(tradable_observations)
    return {
        "metadata": {
            "engine": "V3.5.2 Style Preference Validation & Attribution Engine",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start, "end": end},
            "score_date_count": len(scored_rows_by_date),
            "step_sessions": step_sessions,
            "min_score_sessions": min_score_sessions,
            "horizons": list(horizons),
            "top_n": top_n,
            "baseline": "Opportunity Score TopN across all assets",
            "style_aware": "TopN within the historical dominant style pool; equal averaging is used only for validation statistics.",
        },
        "validation_states": list(VALIDATION_STATES),
        "style_universe": list(STYLE_IDS),
        "summary": {
            "score_start": min(scored_rows_by_date) if scored_rows_by_date else None,
            "score_end": max(scored_rows_by_date) if scored_rows_by_date else None,
            "research_proxy": research_summary,
            "tradable_etf": tradable_summary,
            "edge_read": _edge_read(tradable_summary),
        },
        "observations": {
            "research_proxy": research_observations,
            "tradable_etf": tradable_observations,
        },
        "sample_preferences": sample_preferences,
        "constraints": {
            "research_validation_only": True,
            "style_preference_frozen": True,
            "decision_inputs_only_use_same_day_or_prior_data": True,
            "future_returns_used_only_for_validation_labels": True,
            "no_future_function_in_signal": True,
            "no_etf_weight": True,
            "no_position_sizing": True,
            "no_risk_budget": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization": True,
            "no_best_style_selection_for_trading": True,
        },
        "notes": [
            "The style preference formula is frozen for this validation and uses structural state/features plus same-day opportunity scores.",
            "Future returns are computed after the signal date only to evaluate IC, spread and hit rate.",
            "Style-aware average returns are validation statistics, not portfolio weights or allocation instructions.",
        ],
    }


def write_style_validation(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
