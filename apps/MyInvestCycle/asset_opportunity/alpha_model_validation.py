from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from asset_opportunity.alpha_model_engine import MODEL_DISPATCH, _feature_rows
from asset_opportunity.asset_loader import load_asset_history
from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from asset_opportunity.factor_attribution import summarize_forward_validation
from asset_opportunity.opportunity_score_engine import DEFAULT_BENCHMARK
from asset_opportunity.opportunity_validation import (
    DEFAULT_HORIZONS,
    _forward_return,
    _score_rows_for_date,
    _validation_dates,
)
from asset_opportunity.regime_conditioned_validation import DEFAULT_STATE_PATH, _read_state_signals, _state_for_date
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "alpha_model_validation.json"
MODEL_NAMES = ("opportunity_score", "trend_following", "rotation_alpha", "mean_reversion", "defensive_quality")
ROUTER_MODEL_MAP = {
    "BROAD_BULL": "trend_following",
    "STRUCTURAL_BULL": "rotation_alpha",
    "RANGE": "mean_reversion",
    "BEAR": "defensive_quality",
    "HIGH_CROWDING": "defensive_quality",
}


def _router_bucket(state: Mapping[str, object]) -> str:
    bucket = str(state.get("regime_bucket") or "UNKNOWN")
    if bucket not in ROUTER_MODEL_MAP and str(state.get("structural_state") or "").startswith("BEAR"):
        return "BEAR"
    return bucket


def _model_rows_for_date(mappings, histories, benchmark, as_of: str) -> dict[str, list[dict[str, object]]]:
    baseline = [
        {
            "date": as_of,
            "code": row["code"],
            "name": row["name"],
            "score": row["score"],
            "model": "opportunity_score",
        }
        for row in _score_rows_for_date(mappings, histories, benchmark, as_of)
    ]
    features = _feature_rows(mappings, histories, benchmark, as_of)
    output = {"opportunity_score": baseline}
    for model_name, scorer in MODEL_DISPATCH.items():
        rows = []
        for feature in features:
            scored = scorer(feature)
            rows.append(
                {
                    "date": as_of,
                    "code": feature["code"],
                    "name": feature["name"],
                    "score": scored["model_score"],
                    "model": model_name,
                }
            )
        output[model_name] = rows
    return output


def _observations_for_model(scored_rows_by_date, return_histories, horizons, signals):
    result = {model: {f"{horizon}d": [] for horizon in horizons} for model in MODEL_NAMES}
    for date, by_model in scored_rows_by_date.items():
        state = _state_for_date(date, signals)
        regime_bucket = _router_bucket(state)
        for model_name, rows in by_model.items():
            for row in rows:
                for horizon in horizons:
                    future = _forward_return(return_histories[row["code"]], date, horizon)
                    if future is None:
                        continue
                    result[model_name][f"{horizon}d"].append(
                        {
                            "date": date,
                            "code": row["code"],
                            "score": row["score"],
                            "future_return": round(float(future), 6),
                            "regime_bucket": regime_bucket,
                            "structural_state": state.get("structural_state"),
                            "state_signal_date": state.get("state_signal_date"),
                        }
                    )
    return result


def _summarize_model_observations(observations_by_model) -> dict[str, object]:
    output: dict[str, object] = {}
    for model_name, by_horizon in observations_by_model.items():
        output[model_name] = {}
        for horizon, observations in by_horizon.items():
            grouped: dict[str, list[Mapping[str, object]]] = {}
            for row in observations:
                grouped.setdefault(str(row.get("regime_bucket") or "UNKNOWN"), []).append(row)
            output[model_name][horizon] = {
                regime: summarize_forward_validation(rows)
                for regime, rows in sorted(grouped.items())
            }
    return output


def _router_selected_view(summary_by_model: Mapping[str, object]) -> dict[str, object]:
    selected: dict[str, object] = {}
    for regime, model_name in ROUTER_MODEL_MAP.items():
        model_summary = summary_by_model.get(model_name, {})
        selected[regime] = {
            horizon: values.get(regime)
            for horizon, values in model_summary.items()
            if isinstance(values, Mapping) and values.get(regime) is not None
        }
    return selected


def build_alpha_model_validation(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    state_path: str | Path = DEFAULT_STATE_PATH,
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
    score_dates = _validation_dates(
        benchmark,
        research_histories,
        start_date=start,
        end_date=end,
        step_sessions=step_sessions,
        min_score_sessions=min_score_sessions,
    )
    scored_rows_by_date = {
        date: _model_rows_for_date(mappings, research_histories, benchmark, date)
        for date in score_dates
    }
    signals = _read_state_signals(state_path)
    research_observations = _observations_for_model(scored_rows_by_date, research_histories, horizons, signals)
    tradable_observations = _observations_for_model(scored_rows_by_date, tradable_histories, horizons, signals)
    research_summary = _summarize_model_observations(research_observations)
    tradable_summary = _summarize_model_observations(tradable_observations)
    state_counts = Counter(_router_bucket(_state_for_date(date, signals)) for date in score_dates)
    return {
        "metadata": {
            "engine": "V3.3.3 Regime Alpha Model Validation Engine",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start, "end": end},
            "score_date_count": len(score_dates),
            "score_start": min(score_dates) if score_dates else None,
            "score_end": max(score_dates) if score_dates else None,
            "step_sessions": step_sessions,
            "min_score_sessions": min_score_sessions,
            "horizons": list(horizons),
            "models": list(MODEL_NAMES),
            "formula_frozen": True,
        },
        "summary": {
            "asset_count": len(mappings),
            "source_methods": dict(Counter(mapping.mapping_method for mapping in mappings)),
            "score_date_regime_counts": dict(state_counts),
            "router_model_map": ROUTER_MODEL_MAP,
        },
        "research_proxy_validation": {
            "by_model": research_summary,
            "router_selected": _router_selected_view(research_summary),
        },
        "tradable_etf_validation": {
            "by_model": tradable_summary,
            "router_selected": _router_selected_view(tradable_summary),
        },
        "constraints": {
            "walk_forward": True,
            "state_signal_uses_last_known_signal": True,
            "proxy_return_and_etf_return_separated": True,
            "does_not_change_v3_2_score": True,
            "model_formulas_frozen": True,
            "no_new_factor": True,
            "no_parameter_optimization": True,
            "no_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_backtest_portfolio": True,
        },
    }


def write_alpha_model_validation(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
