from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from asset_opportunity.asset_loader import load_asset_history
from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from asset_opportunity.factor_attribution import summarize_forward_validation
from asset_opportunity.opportunity_score_engine import DEFAULT_BENCHMARK, WEIGHTS
from asset_opportunity.opportunity_validation import (
    DEFAULT_HORIZONS,
    _observations_for_mode,
    _score_rows_for_date,
    _validation_dates,
)
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "regime_opportunity_validation.json"
DEFAULT_STATE_PATH = DATA_DIR / "v2_full_cycle_backtest.json"
REGIME_DIMENSIONS = ("regime_bucket", "structural_state", "macro_state", "market_structure_state", "theme_risk_level")


def _read_state_signals(path: str | Path = DEFAULT_STATE_PATH) -> list[dict[str, object]]:
    state_path = Path(path)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    signals = ((payload.get("signals") or {}).get("v2_structural_refined") or [])
    rows = []
    for item in signals:
        if not isinstance(item, Mapping) or not item.get("date"):
            continue
        rows.append(
            {
                "date": str(item.get("date")),
                "structural_state": str(item.get("structural_state") or "UNKNOWN"),
                "allocation_structural_state": str(item.get("allocation_structural_state") or "UNKNOWN"),
                "macro_state": str(item.get("macro_state") or "UNKNOWN"),
                "market_structure_state": str(item.get("market_structure_state") or "UNKNOWN"),
                "theme_risk_level": str(item.get("theme_risk_level") or "unknown"),
            }
        )
    return sorted(rows, key=lambda row: row["date"])


def _regime_bucket(signal: Mapping[str, object]) -> str:
    theme_risk = str(signal.get("theme_risk_level") or "unknown").lower()
    allocation_state = str(signal.get("allocation_structural_state") or "")
    structural_state = str(signal.get("structural_state") or "UNKNOWN")
    if theme_risk == "high" or allocation_state == "STRUCTURAL_BULL_OVERHEATED":
        return "HIGH_CROWDING"
    if structural_state == "STRUCTURAL_BULL_ROTATION":
        return "STRUCTURAL_BULL"
    if structural_state == "BROAD_BULL":
        return "BROAD_BULL"
    if structural_state == "BEAR":
        return "BEAR"
    if structural_state == "RANGE":
        return "RANGE"
    return structural_state or "UNKNOWN"


def _state_for_date(date: str, signals: list[dict[str, object]]) -> dict[str, object]:
    signal_dates = [str(row["date"]) for row in signals]
    index = bisect_right(signal_dates, date) - 1
    if index < 0:
        return {
            "regime_bucket": "UNKNOWN",
            "structural_state": "UNKNOWN",
            "allocation_structural_state": "UNKNOWN",
            "macro_state": "UNKNOWN",
            "market_structure_state": "UNKNOWN",
            "theme_risk_level": "unknown",
            "state_signal_date": None,
        }
    signal = dict(signals[index])
    signal["regime_bucket"] = _regime_bucket(signal)
    signal["state_signal_date"] = signal["date"]
    return signal


def _attach_regimes(
    observations_by_horizon: Mapping[str, list[dict[str, object]]],
    signals: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for horizon, rows in observations_by_horizon.items():
        enriched: list[dict[str, object]] = []
        for row in rows:
            state = _state_for_date(str(row["date"]), signals)
            enriched.append({**row, **{key: state.get(key) for key in [*REGIME_DIMENSIONS, "allocation_structural_state", "state_signal_date"]}})
        result[horizon] = enriched
    return result


def _summarize_by_dimension(
    observations_by_horizon: Mapping[str, list[Mapping[str, object]]],
    dimension: str,
) -> dict[str, object]:
    output: dict[str, object] = {}
    for horizon, observations in observations_by_horizon.items():
        grouped: dict[str, list[Mapping[str, object]]] = {}
        for row in observations:
            grouped.setdefault(str(row.get(dimension) or "UNKNOWN"), []).append(row)
        output[horizon] = {
            key: summarize_forward_validation(rows)
            for key, rows in sorted(grouped.items())
            if rows
        }
    return output


def build_regime_conditioned_validation(
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
    scored_rows_by_date = {date: _score_rows_for_date(mappings, research_histories, benchmark, date) for date in score_dates}
    signals = _read_state_signals(state_path)
    research = _attach_regimes(
        _observations_for_mode(
            mode="research_proxy_return",
            scored_rows_by_date=scored_rows_by_date,
            return_histories=research_histories,
            horizons=horizons,
        ),
        signals,
    )
    tradable = _attach_regimes(
        _observations_for_mode(
            mode="tradable_etf_return",
            scored_rows_by_date=scored_rows_by_date,
            return_histories=tradable_histories,
            horizons=horizons,
        ),
        signals,
    )
    state_counts = Counter(_state_for_date(date, signals)["regime_bucket"] for date in score_dates)
    return {
        "metadata": {
            "engine": "V3.2.3 Regime-Conditioned Opportunity Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start, "end": end},
            "score_date_count": len(score_dates),
            "score_start": min(score_dates) if score_dates else None,
            "score_end": max(score_dates) if score_dates else None,
            "step_sessions": step_sessions,
            "min_score_sessions": min_score_sessions,
            "horizons": list(horizons),
            "state_source": "data/v2_full_cycle_backtest.json",
            "score_formula": {
                "strength": WEIGHTS,
                "formula_changed_from_v3_2_1": False,
            },
        },
        "regime_rules": {
            "HIGH_CROWDING": "theme_risk_level=high or allocation_structural_state=STRUCTURAL_BULL_OVERHEATED",
            "STRUCTURAL_BULL": "structural_state=STRUCTURAL_BULL_ROTATION and not high crowding",
            "BROAD_BULL": "structural_state=BROAD_BULL and not high crowding",
            "BEAR": "structural_state=BEAR and not high crowding",
            "RANGE": "structural_state=RANGE and not high crowding",
        },
        "summary": {
            "asset_count": len(mappings),
            "source_methods": dict(Counter(mapping.mapping_method for mapping in mappings)),
            "score_date_regime_counts": dict(state_counts),
        },
        "research_proxy_validation": {
            dimension: _summarize_by_dimension(research, dimension)
            for dimension in REGIME_DIMENSIONS
        },
        "tradable_etf_validation": {
            dimension: _summarize_by_dimension(tradable, dimension)
            for dimension in REGIME_DIMENSIONS
        },
        "constraints": {
            "uses_existing_score": True,
            "formula_changed_from_v3_2_1": False,
            "walk_forward": True,
            "no_future_data": True,
            "state_signal_uses_last_known_signal": True,
            "proxy_return_and_etf_return_separated": True,
            "no_new_factor": True,
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
            "Each observation is assigned the latest V2 state signal whose signal date is not after the score date.",
            "This module slices validation results by state; it does not change the score, add factors, or produce allocation.",
        ],
    }


def write_regime_conditioned_validation(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
