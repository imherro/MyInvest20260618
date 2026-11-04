from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from bisect import bisect_right
from pathlib import Path
from typing import Mapping

import pandas as pd

from asset_opportunity.asset_loader import load_asset_history
from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from asset_opportunity.asset_strength_engine import (
    compute_asset_metrics,
    extension_penalty,
    percentile_scores,
    persistence_scores,
)
from asset_opportunity.factor_attribution import summarize_forward_validation
from asset_opportunity.opportunity_ranker import rank_opportunities
from asset_opportunity.opportunity_score_engine import DEFAULT_BENCHMARK, WEIGHTS, crowding_penalty
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date
from theme_risk.valuation_pressure_engine import evaluate_valuation_pressure


DEFAULT_OUTPUT_PATH = DATA_DIR / "asset_opportunity_validation.json"
DEFAULT_HORIZONS = (5, 20, 60)


def _price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "close"])
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    return result.dropna(subset=["trade_date", "close"])[["trade_date", "close"]].sort_values("trade_date").reset_index(drop=True)


def _first_date(frame: pd.DataFrame) -> str | None:
    clean = _price_frame(frame)
    return None if clean.empty else str(clean["trade_date"].iloc[0])


def _last_date(frame: pd.DataFrame) -> str | None:
    clean = _price_frame(frame)
    return None if clean.empty else str(clean["trade_date"].iloc[-1])


def _rows_until(frame: pd.DataFrame, as_of: str) -> int:
    clean = _price_frame(frame)
    return int((clean["trade_date"] <= as_of).sum())


def _forward_return(frame: pd.DataFrame, as_of: str, horizon: int) -> float | None:
    clean = _price_frame(frame)
    if clean.empty:
        return None
    dates = clean["trade_date"].astype(str)
    eligible = clean[dates <= as_of]
    if eligible.empty:
        return None
    current_index = int(eligible.index[-1])
    future_index = current_index + horizon
    if future_index >= len(clean):
        return None
    current = float(clean.loc[current_index, "close"])
    future = float(clean.loc[future_index, "close"])
    if current <= 0:
        return None
    return future / current - 1.0


def _validation_dates(
    benchmark: pd.DataFrame,
    histories: Mapping[str, pd.DataFrame],
    *,
    start_date: str,
    end_date: str,
    step_sessions: int,
    min_score_sessions: int,
) -> list[str]:
    clean_benchmark = _price_frame(benchmark)
    clean_histories = {code: _price_frame(frame) for code, frame in histories.items()}
    history_dates = {
        code: [str(date) for date in frame["trade_date"]]
        for code, frame in clean_histories.items()
    }
    common_start = max(date for date in [_first_date(clean_benchmark), *[_first_date(frame) for frame in clean_histories.values()]] if date)
    common_end = min(date for date in [_last_date(clean_benchmark), *[_last_date(frame) for frame in clean_histories.values()]] if date)
    start = max(start_date, common_start)
    end = min(end_date, common_end)
    dates = [
        str(date)
        for date in clean_benchmark["trade_date"]
        if start <= str(date) <= end
        and all(bisect_right(items, str(date)) >= min_score_sessions for items in history_dates.values())
    ]
    return dates[:: max(1, step_sessions)]


def _historical_theme_risk_payload(mappings, histories: Mapping[str, pd.DataFrame], as_of: str) -> dict[str, object]:
    proxy_themes: dict[str, dict[str, object]] = {}
    proxy_frames: dict[str, pd.DataFrame] = {}
    for mapping in mappings:
        if mapping.research_proxy is None:
            continue
        code = mapping.research_proxy.code
        proxy_themes[code] = {"code": code, "name": mapping.research_proxy.name}
        proxy_frames[code] = histories[mapping.asset_code]
    valuation_pressure = evaluate_valuation_pressure(list(proxy_themes.values()), proxy_frames, as_of)
    pressure_values = [float(item.get("valuation_pressure_score") or 0.0) for item in valuation_pressure]
    top_pressure = sum(pressure_values[:3]) / min(3, len(pressure_values)) if pressure_values else 0.0
    risk_level = "high" if top_pressure >= 72 else "medium" if top_pressure >= 48 else "low"
    return {
        "as_of": as_of,
        "theme_risk_level": risk_level,
        "crowding_score": round(top_pressure, 4),
        "valuation_pressure": valuation_pressure,
        "data_quality": {
            "historical_rebuild": True,
            "source": "loaded research proxy histories",
            "no_future_data": True,
        },
    }


def _score_rows_for_date(mappings, histories: Mapping[str, pd.DataFrame], benchmark: pd.DataFrame, as_of: str) -> list[dict[str, object]]:
    metrics = {
        mapping.asset_code: compute_asset_metrics(mapping.asset_code, histories[mapping.asset_code], benchmark, as_of=as_of)
        for mapping in mappings
    }
    return20_scores = percentile_scores({code: item.get("return_20d") for code, item in metrics.items()})
    return60_scores = percentile_scores({code: item.get("return_60d") for code, item in metrics.items()})
    relative_scores = percentile_scores({code: item.get("relative_60d") for code, item in metrics.items()})
    risk_scores = percentile_scores({code: item.get("risk_adjusted_raw") for code, item in metrics.items()})
    persistence = persistence_scores(histories, as_of=as_of)
    theme_risk = _historical_theme_risk_payload(mappings, histories, as_of)
    rows: list[dict[str, object]] = []
    for mapping in mappings:
        code = mapping.asset_code
        row_metrics = metrics[code]
        momentum = 0.45 * return20_scores[code] + 0.55 * return60_scores[code]
        trend_quality = float((row_metrics.get("trend") or {}).get("score") or 0.0)
        components = {
            "momentum": round(momentum, 4),
            "relative_strength": round(relative_scores[code], 4),
            "trend_quality": round(trend_quality, 4),
            "risk_adjusted": round(risk_scores[code], 4),
            "persistence": round(float(persistence.get(code, 50.0)), 4),
        }
        strength = sum(components[key] * weight for key, weight in WEIGHTS.items())
        penalty = extension_penalty(row_metrics) + crowding_penalty(mapping, theme_risk)
        score = max(0.0, min(100.0, strength - penalty))
        rows.append(
            {
                "date": as_of,
                "code": code,
                "name": mapping.asset_name,
                "mapping_method": mapping.mapping_method,
                "score": round(score, 4),
                "strength": round(strength, 4),
                **components,
                "penalty": round(penalty, 4),
            }
        )
    return rank_opportunities(rows)


def _observations_for_mode(
    *,
    mode: str,
    scored_rows_by_date: Mapping[str, list[Mapping[str, object]]],
    return_histories: Mapping[str, pd.DataFrame],
    horizons: tuple[int, ...],
) -> dict[str, list[dict[str, object]]]:
    by_horizon: dict[str, list[dict[str, object]]] = {f"{horizon}d": [] for horizon in horizons}
    for date, rows in scored_rows_by_date.items():
        for row in rows:
            for horizon in horizons:
                future = _forward_return(return_histories[row["code"]], date, horizon)
                if future is None:
                    continue
                by_horizon[f"{horizon}d"].append(
                    {
                        "mode": mode,
                        "date": date,
                        "code": row["code"],
                        "rank": row["rank"],
                        "score": row["score"],
                        "momentum": row["momentum"],
                        "relative_strength": row["relative_strength"],
                        "trend_quality": row["trend_quality"],
                        "risk_adjusted": row["risk_adjusted"],
                        "persistence": row["persistence"],
                        "future_return": round(float(future), 6),
                    }
                )
    return by_horizon


def build_opportunity_validation(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    step_sessions: int = 20,
    min_score_sessions: int = 260,
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
    scored_rows_by_date = {date: _score_rows_for_date(mappings, research_histories, benchmark, date) for date in dates}
    research_observations = _observations_for_mode(
        mode="research_proxy_return",
        scored_rows_by_date=scored_rows_by_date,
        return_histories=research_histories,
        horizons=horizons,
    )
    tradable_observations = _observations_for_mode(
        mode="tradable_etf_return",
        scored_rows_by_date=scored_rows_by_date,
        return_histories=tradable_histories,
        horizons=horizons,
    )
    return {
        "metadata": {
            "engine": "V3.2.2 Opportunity Score Validation & Factor Attribution",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start, "end": end},
            "score_date_count": len(scored_rows_by_date),
            "step_sessions": step_sessions,
            "min_score_sessions": min_score_sessions,
            "horizons": list(horizons),
            "score_formula": {
                "strength": WEIGHTS,
                "score": "strength - extension_penalty - crowding_penalty",
                "formula_changed_from_v3_2_1": False,
            },
        },
        "summary": {
            "asset_count": len(mappings),
            "source_methods": dict(Counter(mapping.mapping_method for mapping in mappings)),
            "score_start": min(scored_rows_by_date) if scored_rows_by_date else None,
            "score_end": max(scored_rows_by_date) if scored_rows_by_date else None,
        },
        "research_proxy_validation": {
            horizon: summarize_forward_validation(rows)
            for horizon, rows in research_observations.items()
        },
        "tradable_etf_validation": {
            horizon: summarize_forward_validation(rows)
            for horizon, rows in tradable_observations.items()
        },
        "sample_score_dates": [
            {
                "date": date,
                "top_assets": [
                    {"rank": row["rank"], "code": row["code"], "score": row["score"]}
                    for row in rows[:5]
                ],
            }
            for date, rows in list(scored_rows_by_date.items())[-5:]
        ],
        "constraints": {
            "walk_forward": True,
            "no_future_data": True,
            "proxy_return_and_etf_return_separated": True,
            "no_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_backtest_portfolio": True,
            "no_parameter_optimization": True,
            "does_not_modify_v2": True,
        },
        "notes": [
            "research_proxy_validation uses the same research source used by the score, so it tests the factor hypothesis.",
            "tradable_etf_validation uses real ETF future returns only, so it tests whether the research score transfers to tradable instruments.",
            "This module validates ranks and factors; it does not create ETF weights or a portfolio backtest.",
        ],
    }


def write_opportunity_validation(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
