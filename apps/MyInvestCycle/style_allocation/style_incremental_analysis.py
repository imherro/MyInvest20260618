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
from backtest.style_attribution_validation import _read_structural_rows
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date
from style_allocation.style_schema import STYLE_IDS, style_for_asset_code
from style_allocation.style_validation import (
    VALIDATION_STATES,
    build_historical_style_preference,
    structural_row_for_date,
)


DEFAULT_OUTPUT_PATH = DATA_DIR / "style_incremental_analysis.json"
DEFAULT_HORIZONS = (20, 60)
TOP_N = 3


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _mean(values: Iterable[object]) -> float | None:
    clean = [number for number in (_float(value) for value in values) if number is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


def _difference(left: object, right: object) -> float | None:
    left_number = _float(left)
    right_number = _float(right)
    if left_number is None or right_number is None:
        return None
    return round(left_number - right_number, 6)


def _average_forward_return(rows: list[Mapping[str, object]]) -> float | None:
    return _mean(row.get("future_return") for row in rows)


def _ranked_selection(rows: list[Mapping[str, object]], score_key: str, top_n: int) -> list[Mapping[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            _float(row.get(score_key)) if _float(row.get(score_key)) is not None else -9999.0,
            _float(row.get("opportunity_score")) if _float(row.get("opportunity_score")) is not None else -9999.0,
        ),
        reverse=True,
    )[:top_n]


def _selection_payload(rows: list[Mapping[str, object]]) -> list[dict[str, object]]:
    payload = []
    for row in rows:
        payload.append(
            {
                "code": row.get("code"),
                "name": row.get("name"),
                "style": row.get("style"),
                "opportunity_score": row.get("opportunity_score"),
                "style_score": row.get("style_score"),
                "combined_score": row.get("combined_score"),
                "future_return": row.get("future_return"),
            }
        )
    return payload


def _model_ics(rows: list[Mapping[str, object]]) -> dict[str, float | None]:
    valid = [row for row in rows if row.get("future_return") is not None]
    return {
        "baseline_ic": spearman_ic(valid, "opportunity_score"),
        "style_ic": spearman_ic(valid, "style_score"),
        "combined_ic": spearman_ic(valid, "combined_score"),
    }


def _scored_asset_rows(
    *,
    score_rows: list[Mapping[str, object]],
    style_scores: Mapping[str, object],
    return_histories: Mapping[str, pd.DataFrame],
    date_text: str,
    horizon: int,
) -> list[dict[str, object]]:
    rows = []
    for row in score_rows:
        code = str(row.get("code"))
        style_id = style_for_asset_code(code)
        if style_id is None:
            continue
        opportunity_score = _float(row.get("score"))
        style_score = _float(style_scores.get(style_id))
        if opportunity_score is None or style_score is None:
            continue
        history = return_histories.get(code)
        future = None if history is None else _forward_return(history, date_text, horizon)
        rows.append(
            {
                "date": date_text,
                "code": code,
                "name": row.get("name"),
                "style": style_id,
                "rank": row.get("rank"),
                "opportunity_score": round(opportunity_score, 6),
                "style_score": round(style_score, 6),
                "combined_score": round((opportunity_score + style_score) / 2.0, 6),
                "future_return": None if future is None else round(float(future), 6),
            }
        )
    return rows


def _observation_for_date(
    *,
    mode: str,
    date_text: str,
    validation_state: str,
    dominant_style: str,
    rows: list[Mapping[str, object]],
    horizon: int,
    top_n: int,
) -> dict[str, object] | None:
    baseline_selection = _ranked_selection(rows, "opportunity_score", top_n)
    style_selection = _ranked_selection(rows, "style_score", top_n)
    combined_selection = _ranked_selection(rows, "combined_score", top_n)
    baseline_return = _average_forward_return(baseline_selection)
    style_return = _average_forward_return(style_selection)
    combined_return = _average_forward_return(combined_selection)
    if baseline_return is None or style_return is None or combined_return is None:
        return None

    ics = _model_ics(rows)
    baseline_codes = {str(row.get("code")) for row in baseline_selection}
    style_codes = {str(row.get("code")) for row in style_selection}
    combined_codes = {str(row.get("code")) for row in combined_selection}
    return {
        "mode": mode,
        "date": date_text,
        "horizon": f"{horizon}d",
        "validation_state": validation_state,
        "dominant_style": dominant_style,
        "baseline_return": round(float(baseline_return), 6),
        "style_return": round(float(style_return), 6),
        "combined_return": round(float(combined_return), 6),
        "style_minus_baseline_return": _difference(style_return, baseline_return),
        "combined_minus_baseline_return": _difference(combined_return, baseline_return),
        "combined_minus_style_return": _difference(combined_return, style_return),
        **ics,
        "style_ic_minus_baseline_ic": _difference(ics.get("style_ic"), ics.get("baseline_ic")),
        "combined_ic_minus_baseline_ic": _difference(ics.get("combined_ic"), ics.get("baseline_ic")),
        "combined_ic_minus_style_ic": _difference(ics.get("combined_ic"), ics.get("style_ic")),
        "hit": {
            "style_beats_baseline": bool(style_return > baseline_return),
            "combined_beats_baseline": bool(combined_return > baseline_return),
            "combined_beats_style": bool(combined_return > style_return),
        },
        "selection_overlap": {
            "style_vs_baseline_count": len(style_codes & baseline_codes),
            "combined_vs_baseline_count": len(combined_codes & baseline_codes),
            "combined_vs_style_count": len(combined_codes & style_codes),
            "style_vs_baseline_ratio": round(len(style_codes & baseline_codes) / max(1, top_n), 6),
            "combined_vs_baseline_ratio": round(len(combined_codes & baseline_codes) / max(1, top_n), 6),
            "combined_vs_style_ratio": round(len(combined_codes & style_codes) / max(1, top_n), 6),
        },
        "selections": {
            "baseline": _selection_payload(baseline_selection),
            "style": _selection_payload(style_selection),
            "combined": _selection_payload(combined_selection),
        },
    }


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
        for horizon in horizons:
            rows = _scored_asset_rows(
                score_rows=score_rows,
                style_scores=preference["style_scores"],
                return_histories=return_histories,
                date_text=date_text,
                horizon=horizon,
            )
            observation = _observation_for_date(
                mode=mode,
                date_text=date_text,
                validation_state=str(preference["validation_state"]),
                dominant_style=str(preference["dominant_style"]),
                rows=rows,
                horizon=horizon,
                top_n=top_n,
            )
            if observation is not None:
                result[f"{horizon}d"].append(observation)
    return result


def _positive_rate(rows: list[Mapping[str, object]], key: str) -> float | None:
    values = [_float(row.get(key)) for row in rows]
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(1 for value in clean if value > 0) / len(clean), 6)


def _hit_rate(rows: list[Mapping[str, object]], key: str) -> float | None:
    values = [
        bool((row.get("hit") or {}).get(key))
        for row in rows
        if isinstance(row.get("hit"), Mapping) and key in (row.get("hit") or {})
    ]
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values), 6)


def _summary(rows: list[Mapping[str, object]]) -> dict[str, object]:
    return {
        "date_count": len({str(row.get("date")) for row in rows}),
        "observation_count": len(rows),
        "returns": {
            "baseline": _mean(row.get("baseline_return") for row in rows),
            "style": _mean(row.get("style_return") for row in rows),
            "combined": _mean(row.get("combined_return") for row in rows),
            "style_minus_baseline": _mean(row.get("style_minus_baseline_return") for row in rows),
            "combined_minus_baseline": _mean(row.get("combined_minus_baseline_return") for row in rows),
            "combined_minus_style": _mean(row.get("combined_minus_style_return") for row in rows),
        },
        "rank_ic": {
            "baseline": _mean(row.get("baseline_ic") for row in rows),
            "style": _mean(row.get("style_ic") for row in rows),
            "combined": _mean(row.get("combined_ic") for row in rows),
            "style_minus_baseline": _mean(row.get("style_ic_minus_baseline_ic") for row in rows),
            "combined_minus_baseline": _mean(row.get("combined_ic_minus_baseline_ic") for row in rows),
            "combined_minus_style": _mean(row.get("combined_ic_minus_style_ic") for row in rows),
            "combined_positive_incremental_rate": _positive_rate(rows, "combined_ic_minus_baseline_ic"),
        },
        "hit_rate": {
            "style_beats_baseline": _hit_rate(rows, "style_beats_baseline"),
            "combined_beats_baseline": _hit_rate(rows, "combined_beats_baseline"),
            "combined_beats_style": _hit_rate(rows, "combined_beats_style"),
        },
        "selection_overlap": {
            "style_vs_baseline_ratio": _mean((row.get("selection_overlap") or {}).get("style_vs_baseline_ratio") for row in rows),
            "combined_vs_baseline_ratio": _mean((row.get("selection_overlap") or {}).get("combined_vs_baseline_ratio") for row in rows),
            "combined_vs_style_ratio": _mean((row.get("selection_overlap") or {}).get("combined_vs_style_ratio") for row in rows),
        },
    }


def _group_summary(rows: list[Mapping[str, object]]) -> dict[str, object]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("validation_state") or "unknown")].append(row)
    for state in VALIDATION_STATES:
        grouped.setdefault(state, [])
    return {state: _summary(items) for state, items in sorted(grouped.items())}


def _summaries(observations: Mapping[str, list[Mapping[str, object]]]) -> dict[str, object]:
    return {
        horizon: {
            "overall": _summary(list(rows)),
            "by_state": _group_summary(list(rows)),
        }
        for horizon, rows in observations.items()
    }


def _edge_read(tradable_summary: Mapping[str, object]) -> dict[str, object]:
    h20 = ((tradable_summary.get("20d") or {}).get("overall") or {})
    h60 = ((tradable_summary.get("60d") or {}).get("overall") or {})
    h20_return_gap = ((h20.get("returns") or {}).get("combined_minus_baseline"))
    h60_return_gap = ((h60.get("returns") or {}).get("combined_minus_baseline"))
    h20_ic_gap = ((h20.get("rank_ic") or {}).get("combined_minus_baseline"))
    h60_ic_gap = ((h60.get("rank_ic") or {}).get("combined_minus_baseline"))
    h20_hit = ((h20.get("hit_rate") or {}).get("combined_beats_baseline"))
    h60_hit = ((h60.get("hit_rate") or {}).get("combined_beats_baseline"))

    def positive(value: object) -> bool:
        number = _float(value)
        return number is not None and number > 0

    def hit_ok(value: object) -> bool:
        number = _float(value)
        return number is not None and number > 0.5

    if (
        positive(h20_return_gap)
        and positive(h60_return_gap)
        and positive(h20_ic_gap)
        and positive(h60_ic_gap)
        and hit_ok(h20_hit)
        and hit_ok(h60_hit)
    ):
        status = "incremental_positive"
    elif positive(h20_return_gap) and positive(h20_ic_gap):
        status = "weak_short_horizon_trace"
    else:
        status = "no_clear_incremental_edge"

    return {
        "style_incremental_edge_status": status,
        "tradable_20d_combined_minus_baseline_return": h20_return_gap,
        "tradable_60d_combined_minus_baseline_return": h60_return_gap,
        "tradable_20d_combined_ic_minus_baseline": h20_ic_gap,
        "tradable_60d_combined_ic_minus_baseline": h60_ic_gap,
        "tradable_20d_combined_hit_rate": h20_hit,
        "tradable_60d_combined_hit_rate": h60_hit,
        "interpretation": (
            "Combined is a fixed 50/50 diagnostic blend of Opportunity Score and Style Preference. "
            "It is considered useful only if it improves forward return spread, rank IC and hit rate without changing model weights or allocation rules."
        ),
    }


def _sample_observations(observations: Mapping[str, list[Mapping[str, object]]], limit: int = 5) -> list[dict[str, object]]:
    rows = list((observations.get("20d") or []))[-limit:]
    return [
        {
            "date": row.get("date"),
            "validation_state": row.get("validation_state"),
            "dominant_style": row.get("dominant_style"),
            "baseline_return": row.get("baseline_return"),
            "style_return": row.get("style_return"),
            "combined_return": row.get("combined_return"),
            "combined_minus_baseline_return": row.get("combined_minus_baseline_return"),
            "baseline_selection": row.get("selections", {}).get("baseline"),
            "style_selection": row.get("selections", {}).get("style"),
            "combined_selection": row.get("selections", {}).get("combined"),
        }
        for row in rows
    ]


def build_style_incremental_analysis(
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
    research_summary = _summaries(research_observations)
    tradable_summary = _summaries(tradable_observations)
    return {
        "metadata": {
            "engine": "V3.5.7 Style Incremental Information Test",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start, "end": end},
            "score_date_count": len(scored_rows_by_date),
            "step_sessions": step_sessions,
            "min_score_sessions": min_score_sessions,
            "horizons": list(horizons),
            "top_n": top_n,
            "validation_scope": "STYLE_INCREMENTAL_INFORMATION_ONLY",
        },
        "model_definitions": {
            "baseline": "Opportunity Score ranking across all assets.",
            "style": "Style Preference score assigned to each asset's style; opportunity score is used only as a deterministic tie-breaker in TopN selection.",
            "combined": "Fixed 50/50 average of Opportunity Score and Style Preference score; no weight search or parameter optimization.",
        },
        "validation_states": list(VALIDATION_STATES),
        "style_universe": list(STYLE_IDS),
        "summary": {
            "score_start": min(scored_rows_by_date) if scored_rows_by_date else None,
            "score_end": max(scored_rows_by_date) if scored_rows_by_date else None,
            "research_proxy": research_summary,
            "tradable_etf": tradable_summary,
            "edge_read": _edge_read(tradable_summary),
            "interpretation": (
                "This test asks whether Style Preference adds independent information beyond Opportunity Score. "
                "A weak or negative combined-minus-baseline result means style should remain research attribution instead of becoming allocation."
            ),
        },
        "observations": {
            "research_proxy": research_observations,
            "tradable_etf": tradable_observations,
        },
        "sample_observations": {
            "tradable_etf": _sample_observations(tradable_observations),
            "research_proxy": _sample_observations(research_observations),
        },
        "constraints": {
            "research_validation_only": True,
            "style_preference_formula_unchanged": True,
            "opportunity_score_formula_unchanged": True,
            "router_unchanged": True,
            "alpha_model_unchanged": True,
            "combined_weight_fixed_not_optimized": True,
            "decision_inputs_only_use_same_day_or_prior_data": True,
            "future_returns_used_only_for_validation_metrics": True,
            "no_future_function_in_signal": True,
            "no_allocation": True,
            "no_style_weight": True,
            "no_etf_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization": True,
        },
        "notes": [
            "The style model is intentionally blunt: it ranks by same-day style preference score, then opportunity score only as a tie-breaker.",
            "The combined model uses a fixed 50/50 blend to avoid selecting the best historical weight.",
            "Future returns are used only after the signal date to compute IC, TopN return spread and hit rate.",
        ],
    }


def write_style_incremental_analysis(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
