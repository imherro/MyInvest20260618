from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean, median
from typing import Mapping, Sequence

import pandas as pd

from asset_opportunity.asset_loader import load_asset_history
from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from asset_opportunity.opportunity_context_features import (
    CONTEXT_INPUTS,
    DEFAULT_BENCHMARKS,
    DEFAULT_START_DATE,
    _asset_features,
    _latest_style_context,
    _price_frame,
    _read_json,
)
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "opportunity_feature_validation.json"
HORIZONS = (5, 20, 60)
FEATURE_DEFINITIONS = (
    ("momentum", "return_20d", "momentum.return_20d"),
    ("momentum", "return_60d", "momentum.return_60d"),
    ("momentum", "return_120d", "momentum.return_120d"),
    ("relative_strength", "relative_return_60d_vs_hs300", "relative_strength.relative_return_60d_vs_hs300"),
    ("relative_strength", "relative_return_60d_vs_csi500", "relative_strength.relative_return_60d_vs_csi500"),
    ("trend", "distance_to_ma60", "trend.distance_to_ma60"),
    ("trend", "distance_to_ma120", "trend.distance_to_ma120"),
    ("trend", "distance_to_ma250", "trend.distance_to_ma250"),
    ("risk", "volatility_60d_annualized", "risk.volatility_60d_annualized"),
    ("risk", "max_drawdown_120d", "risk.max_drawdown_120d"),
    ("risk", "price_extension_252d_percentile", "risk.price_extension_252d_percentile"),
    ("structure", "industry_breadth", "structure.industry_breadth"),
    ("structure", "theme_persistence", "structure.theme_persistence"),
    ("structure", "crowding_score", "structure.crowding_score"),
)
MIN_ASSETS_PER_IC = 6


def _project_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _feature_value(asset_features: Mapping[str, object], group: str, field: str) -> float | None:
    group_payload = asset_features.get(group)
    if not isinstance(group_payload, Mapping):
        return None
    field_payload = group_payload.get(field)
    if not isinstance(field_payload, Mapping):
        return None
    value = field_payload.get("value")
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _source_asset(asset_code: str, asset_name: str, category: str) -> dict[str, object]:
    return {
        "code": asset_code,
        "name": asset_name,
        "type": "etf",
        "category": category,
        "source": "Tushare fund_daily",
        "benchmark": asset_code,
        "enabled": True,
    }


def _forward_return(frame: pd.DataFrame, signal_date: str, horizon: int) -> float | None:
    prices = _price_frame(frame, "20991231")
    if prices.empty:
        return None
    eligible = prices[prices["trade_date"] <= signal_date]
    if eligible.empty:
        return None
    signal_idx = int(eligible.index[-1])
    forward_idx = signal_idx + horizon
    if forward_idx >= len(prices):
        return None
    start = float(prices.loc[signal_idx, "close"])
    end = float(prices.loc[forward_idx, "close"])
    if start <= 0:
        return None
    return end / start - 1.0


def _safe_spearman(values: Sequence[float], returns: Sequence[float]) -> float | None:
    if len(values) < MIN_ASSETS_PER_IC or len(returns) < MIN_ASSETS_PER_IC:
        return None
    left = pd.Series(values, dtype=float)
    right = pd.Series(returns, dtype=float)
    if left.nunique(dropna=True) < 2 or right.nunique(dropna=True) < 2:
        return None
    value = left.rank(method="average").corr(right.rank(method="average"))
    return round(float(value), 6) if value is not None and not pd.isna(value) else None


def _ic_status(mean_ic: float | None, sample_count: int) -> str:
    if sample_count < 12 or mean_ic is None:
        return "insufficient"
    abs_ic = abs(mean_ic)
    if abs_ic >= 0.08:
        return "visible"
    if abs_ic >= 0.04:
        return "weak"
    return "flat"


def _series_summary(values: Sequence[float | None]) -> dict[str, object]:
    clean = [float(value) for value in values if value is not None and not pd.isna(value)]
    if not clean:
        return {
            "sample_count": 0,
            "mean_ic": None,
            "median_ic": None,
            "positive_share": None,
            "negative_share": None,
        }
    positive = sum(1 for value in clean if value > 0)
    negative = sum(1 for value in clean if value < 0)
    return {
        "sample_count": len(clean),
        "mean_ic": round(mean(clean), 6),
        "median_ic": round(median(clean), 6),
        "positive_share": round(positive / len(clean), 6),
        "negative_share": round(negative / len(clean), 6),
    }


def _row_ic(
    feature_rows: Sequence[Mapping[str, object]],
    *,
    feature_group: str,
    feature_field: str,
    horizon: int,
    return_key: str,
) -> dict[str, object]:
    values = []
    returns = []
    asset_count = 0
    for row in feature_rows:
        features = row.get("features")
        if not isinstance(features, Mapping):
            continue
        value = _feature_value(features, feature_group, feature_field)
        forward = row.get(return_key)
        if value is None or forward is None:
            continue
        values.append(value)
        returns.append(float(forward))
        asset_count += 1
    return {
        "horizon": horizon,
        "asset_count": asset_count,
        "ic": _safe_spearman(values, returns),
    }


def _regime_summary(items: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[float | None]] = defaultdict(list)
    for item in items:
        grouped[str(item.get("two_axis_label") or "UNKNOWN")].append(item.get("ic"))
    return {
        label: _series_summary(values)
        for label, values in sorted(grouped.items())
    }


def _feature_result(
    observations: Sequence[Mapping[str, object]],
    *,
    feature_group: str,
    feature_field: str,
    feature_key: str,
    horizon: int,
) -> dict[str, object]:
    research_ics = [
        _row_ic(obs["asset_rows"], feature_group=feature_group, feature_field=feature_field, horizon=horizon, return_key="research_forward_return") | {
            "date": obs["date"],
            "two_axis_label": obs["two_axis_label"],
        }
        for obs in observations
    ]
    tradable_ics = [
        _row_ic(obs["asset_rows"], feature_group=feature_group, feature_field=feature_field, horizon=horizon, return_key="tradable_forward_return") | {
            "date": obs["date"],
            "two_axis_label": obs["two_axis_label"],
        }
        for obs in observations
    ]
    research_summary = _series_summary([item["ic"] for item in research_ics])
    tradable_summary = _series_summary([item["ic"] for item in tradable_ics])
    return {
        "feature_group": feature_group,
        "feature_field": feature_field,
        "feature_key": feature_key,
        "horizon_sessions": horizon,
        "research_proxy": {
            **research_summary,
            "status": _ic_status(research_summary["mean_ic"], research_summary["sample_count"]),
            "regime_breakdown": _regime_summary(research_ics),
        },
        "tradable_etf": {
            **tradable_summary,
            "status": _ic_status(tradable_summary["mean_ic"], tradable_summary["sample_count"]),
            "regime_breakdown": _regime_summary(tradable_ics),
        },
        "interpretation": "feature_validation_only_not_a_score_or_rank",
    }


def _context_rows(context_payload: Mapping[str, object], start: str, end: str) -> list[dict[str, object]]:
    rows = [row for row in context_payload.get("rows") or [] if isinstance(row, Mapping)]
    result = []
    for row in rows:
        date = str(row.get("date") or "")
        if start <= date <= end:
            result.append(
                {
                    "date": date,
                    "two_axis_label": row.get("two_axis_label") or "UNKNOWN",
                    "market_phase": row.get("market_phase") or "UNKNOWN",
                    "risk_state": row.get("risk_state") or "UNKNOWN",
                    "opportunity_state": row.get("opportunity_state") or "UNKNOWN",
                }
            )
    return result


def _build_observations(
    *,
    dates: Sequence[Mapping[str, object]],
    mappings,
    research_histories: Mapping[str, pd.DataFrame],
    tradable_histories: Mapping[str, pd.DataFrame],
    benchmarks: Mapping[str, pd.DataFrame],
    style_payload: Mapping[str, object],
    horizon: int,
) -> list[dict[str, object]]:
    observations = []
    for item in dates:
        date = str(item["date"])
        style_row = _latest_style_context(style_payload, date)
        asset_rows = []
        for mapping in mappings:
            research_history = research_histories[mapping.asset_code]
            asset_feature_row = _asset_features(
                mapping,
                research_history,
                {key: _price_frame(frame, date) for key, frame in benchmarks.items()},
                as_of=date,
                style_row=style_row,
            )
            asset_rows.append(
                {
                    **asset_feature_row,
                    "research_forward_return": _forward_return(research_history, date, horizon),
                    "tradable_forward_return": _forward_return(tradable_histories[mapping.asset_code], date, horizon),
                }
            )
        observations.append({**item, "asset_rows": asset_rows})
    return observations


def _status_counts(results: Sequence[Mapping[str, object]], source_key: str) -> dict[str, int]:
    counter = defaultdict(int)
    for result in results:
        status = _as_status(result, source_key)
        counter[status] += 1
    return dict(sorted(counter.items()))


def _as_status(result: Mapping[str, object], source_key: str) -> str:
    source = result.get(source_key)
    return str(source.get("status") if isinstance(source, Mapping) else "unknown")


def build_opportunity_feature_validation(
    as_of: str | int = "20991231",
    *,
    start_date: str | int = DEFAULT_START_DATE,
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    cache_only: bool = True,
) -> dict[str, object]:
    requested_as_of = normalize_trade_date(as_of)
    start = normalize_trade_date(start_date)
    mappings = [mapping for mapping in read_asset_proxy_registry(registry_path) if mapping.enabled]
    research_histories = {
        mapping.asset_code: load_research_proxy_history(mapping, start, requested_as_of, cache_only=cache_only)
        for mapping in mappings
    }
    tradable_histories = {
        mapping.asset_code: load_asset_history(_source_asset(mapping.asset_code, mapping.asset_name, mapping.asset_category), start, requested_as_of, cache_only=True)
        for mapping in mappings
    }
    benchmarks = {
        key: read_benchmark_cache(meta["code"], start, requested_as_of)
        for key, meta in DEFAULT_BENCHMARKS.items()
    }
    context_payloads = {name: _read_json(path) for name, path in CONTEXT_INPUTS.items()}
    dates = _context_rows(context_payloads["two_axis_context"], start, requested_as_of)
    style_payload = context_payloads["historical_style_context"]
    results = []
    observation_counts: dict[int, int] = {}
    for horizon in HORIZONS:
        observations = _build_observations(
            dates=dates,
            mappings=mappings,
            research_histories=research_histories,
            tradable_histories=tradable_histories,
            benchmarks=benchmarks,
            style_payload=style_payload,
            horizon=horizon,
        )
        observation_counts[horizon] = len(observations)
        for group, field, key in FEATURE_DEFINITIONS:
            results.append(
                _feature_result(
                    observations,
                    feature_group=group,
                    feature_field=field,
                    feature_key=key,
                    horizon=horizon,
                )
            )
    return {
        "metadata": {
            "engine": "V7.3 Opportunity Feature Effectiveness Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "requested_as_of": requested_as_of,
            "start_date": start,
            "feature_source_engine": "V7.2 Structural Opportunity Context Feature Audit",
            "registry": _project_path(registry_path),
            "purpose": "Validate fixed opportunity context features by IC only; no score, ranking, allocation, or trade signal.",
        },
        "summary": {
            "feature_count": len(FEATURE_DEFINITIONS),
            "horizons": list(HORIZONS),
            "context_observation_count": len(dates),
            "observation_counts_by_horizon": observation_counts,
            "result_count": len(results),
            "research_proxy_status_counts": _status_counts(results, "research_proxy"),
            "tradable_etf_status_counts": _status_counts(results, "tradable_etf"),
            "ready_for_scoring": False,
            "ready_for_ranking": False,
            "ready_for_allocation": False,
            "ready_for_trade": False,
            "key_read": "V7.3 audits whether fixed V7.2 features have information value; it does not create scores, ranks, Top N, allocations, or trades.",
        },
        "feature_results": results,
        "time_safety": {
            "requested_as_of": requested_as_of,
            "feature_dates_from_v6_context_rows": True,
            "feature_values_use_history_lte_signal_date": True,
            "forward_returns_used_only_as_validation_labels": True,
            "future_returns_not_used_in_feature_values": True,
            "research_proxy_and_tradable_etf_validated_separately": True,
            "future_labels_used_for_scoring": False,
        },
        "data_quality": {
            "cache_only": cache_only,
            "asset_count": len(mappings),
            "min_assets_per_ic": MIN_ASSETS_PER_IC,
            "feature_definitions_fixed": True,
            "horizons_fixed_by_design": True,
            "no_scoring": True,
            "no_ranking": True,
            "no_top_n": True,
            "no_allocation": True,
            "no_backtest": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "effectiveness_audit_only": True,
            "does_not_create_opportunity_score": True,
            "does_not_rank_assets": True,
            "does_not_select_top_assets": True,
            "does_not_generate_position": True,
            "no_percentage_exposure": True,
            "no_etf_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def write_opportunity_feature_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
