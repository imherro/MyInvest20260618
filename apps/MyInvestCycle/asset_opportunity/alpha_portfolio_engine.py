from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Mapping

from asset_opportunity.alpha_model_portfolio import TOP_N_VALUES, select_top_n, selection_codes
from asset_opportunity.alpha_model_validation import ROUTER_MODEL_MAP, _model_rows_for_date, _router_bucket
from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from asset_opportunity.opportunity_score_engine import DEFAULT_BENCHMARK
from asset_opportunity.opportunity_validation import DEFAULT_HORIZONS, _validation_dates
from asset_opportunity.regime_conditioned_validation import DEFAULT_STATE_PATH, _read_state_signals, _state_for_date
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date


def build_alpha_portfolio_plan(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    state_path: str | Path = DEFAULT_STATE_PATH,
    top_n_values: tuple[int, ...] = TOP_N_VALUES,
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
    benchmark = read_benchmark_cache(DEFAULT_BENCHMARK, start, end)
    score_dates = _validation_dates(
        benchmark,
        research_histories,
        start_date=start,
        end_date=end,
        step_sessions=step_sessions,
        min_score_sessions=min_score_sessions,
    )
    signals = _read_state_signals(state_path)
    plan_rows: list[dict[str, object]] = []
    for date in score_dates:
        by_model = _model_rows_for_date(mappings, research_histories, benchmark, date)
        state = _state_for_date(date, signals)
        regime = _router_bucket(state)
        selected_model = ROUTER_MODEL_MAP.get(regime)
        if selected_model is None:
            continue
        for top_n in top_n_values:
            for model_label, source_rows in (
                ("opportunity_score", by_model["opportunity_score"]),
                ("router_selected_model", by_model[selected_model]),
            ):
                selected = select_top_n(source_rows, top_n)
                plan_rows.append(
                    {
                        "signal_date": date,
                        "model_label": model_label,
                        "selected_model": selected_model,
                        "regime": regime,
                        "top_n": top_n,
                        "selected_assets": [
                            {"code": row["code"], "score": round(float(row["score"]), 4)}
                            for row in selected
                        ],
                        "selected_codes": sorted(selection_codes(selected)),
                    }
                )
    return {
        "metadata": {
            "engine": "V3.4.2 Alpha Portfolio Plan",
            "window": {"start": start, "end": end},
            "score_date_count": len(score_dates),
            "top_n_values": list(top_n_values),
            "step_sessions": step_sessions,
        },
        "summary": {
            "asset_count": len(mappings),
            "source_methods": dict(Counter(mapping.mapping_method for mapping in mappings)),
            "plan_rows": len(plan_rows),
        },
        "plan": plan_rows,
        "constraints": {
            "equal_weight_plan_only": True,
            "top_n_fixed": True,
            "no_weight_optimization": True,
            "no_trade_signal": True,
        },
    }
