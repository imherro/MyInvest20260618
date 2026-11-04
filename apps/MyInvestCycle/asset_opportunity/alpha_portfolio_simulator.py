from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from asset_opportunity.alpha_model_portfolio import TOP_N_VALUES, select_top_n, selection_codes, turnover_proxy
from asset_opportunity.alpha_model_validation import ROUTER_MODEL_MAP, _model_rows_for_date, _router_bucket
from asset_opportunity.asset_loader import load_asset_history
from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from asset_opportunity.opportunity_score_engine import DEFAULT_BENCHMARK
from asset_opportunity.opportunity_validation import DEFAULT_HORIZONS, _validation_dates
from asset_opportunity.regime_conditioned_validation import DEFAULT_STATE_PATH, _read_state_signals, _state_for_date
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "alpha_portfolio_simulation.json"
SIMULATION_MODELS = ("opportunity_score", "router_selected_model")


def _price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "close"])
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    return result.dropna(subset=["trade_date", "close"])[["trade_date", "close"]].sort_values("trade_date").reset_index(drop=True)


def _forward_return_tplus1(frame: pd.DataFrame, as_of: str, horizon: int) -> float | None:
    clean = _price_frame(frame)
    if clean.empty:
        return None
    eligible = clean[clean["trade_date"] <= as_of]
    if eligible.empty:
        return None
    signal_index = int(eligible.index[-1])
    entry_index = signal_index + 1
    exit_index = entry_index + horizon
    if exit_index >= len(clean):
        return None
    entry = float(clean.loc[entry_index, "close"])
    exit_price = float(clean.loc[exit_index, "close"])
    if entry <= 0:
        return None
    return exit_price / entry - 1.0


def _mean(values: Iterable[float]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _selection_return(rows: list[Mapping[str, object]], histories: Mapping[str, pd.DataFrame], date: str, horizon: int) -> float | None:
    returns = [
        _forward_return_tplus1(histories[str(row["code"])], date, horizon)
        for row in rows
        if str(row["code"]) in histories
    ]
    return _mean(value for value in returns if value is not None)


def _universe_return(codes: list[str], histories: Mapping[str, pd.DataFrame], date: str, horizon: int) -> float | None:
    returns = [_forward_return_tplus1(histories[code], date, horizon) for code in codes if code in histories]
    return _mean(value for value in returns if value is not None)


def _summarize(records: list[Mapping[str, object]]) -> dict[str, object]:
    if not records:
        return {"observation_count": 0}
    returns = [float(row["topn_return"]) for row in records if row.get("topn_return") is not None]
    universe = [float(row["universe_return"]) for row in records if row.get("universe_return") is not None]
    spreads = [float(row["spread"]) for row in records if row.get("spread") is not None]
    hits = [1.0 if float(row["spread"]) > 0 else 0.0 for row in records if row.get("spread") is not None]
    turnover_values = [float(row["turnover_proxy"]) for row in records if row.get("turnover_proxy") is not None]
    return {
        "observation_count": len(records),
        "avg_topn_return": None if not returns else round(sum(returns) / len(returns), 6),
        "avg_universe_return": None if not universe else round(sum(universe) / len(universe), 6),
        "avg_spread": None if not spreads else round(sum(spreads) / len(spreads), 6),
        "hit_rate": None if not hits else round(sum(hits) / len(hits), 6),
        "turnover_proxy": None if not turnover_values else round(sum(turnover_values) / len(turnover_values), 6),
    }


def _simulate_mode(scored_rows_by_date, return_histories, signals, horizons, top_n_values) -> dict[str, object]:
    all_codes = sorted({row["code"] for by_model in scored_rows_by_date.values() for rows in by_model.values() for row in rows})
    records: dict[str, dict[str, dict[str, list[dict[str, object]]]]] = {
        model: {f"top{top_n}": {f"{horizon}d": [] for horizon in horizons} for top_n in top_n_values}
        for model in SIMULATION_MODELS
    }
    previous_codes: dict[tuple[str, int], set[str] | None] = {}
    for date, by_model in scored_rows_by_date.items():
        state = _state_for_date(date, signals)
        regime = _router_bucket(state)
        selected_model_name = ROUTER_MODEL_MAP.get(regime)
        if not selected_model_name:
            continue
        model_sources = {
            "opportunity_score": by_model["opportunity_score"],
            "router_selected_model": by_model[selected_model_name],
        }
        for model_label, rows in model_sources.items():
            for top_n in top_n_values:
                selected = select_top_n(rows, top_n)
                current_codes = selection_codes(selected)
                turnover = turnover_proxy(previous_codes.get((model_label, top_n)), current_codes)
                previous_codes[(model_label, top_n)] = current_codes
                for horizon in horizons:
                    topn_return = _selection_return(selected, return_histories, date, horizon)
                    universe_return = _universe_return(all_codes, return_histories, date, horizon)
                    if topn_return is None or universe_return is None:
                        continue
                    records[model_label][f"top{top_n}"][f"{horizon}d"].append(
                        {
                            "date": date,
                            "regime": regime,
                            "selected_model": selected_model_name,
                            "selected_assets": [
                                {"code": row["code"], "score": round(float(row["score"]), 4)}
                                for row in selected
                            ],
                            "topn_return": round(topn_return, 6),
                            "universe_return": round(universe_return, 6),
                            "spread": round(topn_return - universe_return, 6),
                            "turnover_proxy": turnover,
                        }
                    )
    return {
        model: {
            topn: {horizon: _summarize(rows) for horizon, rows in by_horizon.items()}
            for topn, by_horizon in by_topn.items()
        }
        for model, by_topn in records.items()
    } | {
        "samples": {
            model: {
                topn: {
                    horizon: rows[-3:]
                    for horizon, rows in by_horizon.items()
                }
                for topn, by_horizon in by_topn.items()
            }
            for model, by_topn in records.items()
        }
    }


def build_alpha_portfolio_simulation(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    state_path: str | Path = DEFAULT_STATE_PATH,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    step_sessions: int = 20,
    top_n_values: tuple[int, ...] = TOP_N_VALUES,
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
    state_counts = Counter(_router_bucket(_state_for_date(date, signals)) for date in score_dates)
    return {
        "metadata": {
            "engine": "V3.4.1 Alpha Model Portfolio Simulation Foundation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start, "end": end},
            "score_date_count": len(score_dates),
            "score_start": min(score_dates) if score_dates else None,
            "score_end": max(score_dates) if score_dates else None,
            "step_sessions": step_sessions,
            "horizons": list(horizons),
            "top_n_values": list(top_n_values),
            "entry_rule": "T+1 close simulation",
        },
        "summary": {
            "asset_count": len(mappings),
            "source_methods": dict(Counter(mapping.mapping_method for mapping in mappings)),
            "score_date_regime_counts": dict(state_counts),
            "router_model_map": ROUTER_MODEL_MAP,
        },
        "research_proxy_simulation": _simulate_mode(scored_rows_by_date, research_histories, signals, horizons, top_n_values),
        "tradable_etf_simulation": _simulate_mode(scored_rows_by_date, tradable_histories, signals, horizons, top_n_values),
        "constraints": {
            "simulation_only": True,
            "top_n_fixed": True,
            "t_plus_1_entry": True,
            "walk_forward": True,
            "state_signal_uses_last_known_signal": True,
            "proxy_return_and_etf_return_separated": True,
            "model_formulas_frozen": True,
            "no_parameter_optimization": True,
            "no_real_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def write_alpha_portfolio_simulation(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
