from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Callable, Mapping

import pandas as pd

from asset_opportunity.alpha_models import (
    score_defensive_quality,
    score_mean_reversion,
    score_rotation_alpha,
    score_trend_following,
)
from asset_opportunity.alpha_regime_router import build_alpha_regime_decision
from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from asset_opportunity.asset_strength_engine import (
    compute_asset_metrics,
    extension_penalty,
    percentile_scores,
    persistence_scores,
)
from asset_opportunity.opportunity_ranker import rank_opportunities
from asset_opportunity.opportunity_score_engine import DEFAULT_BENCHMARK
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "alpha_model_snapshot.json"
MODEL_DISPATCH: dict[str, Callable[[Mapping[str, object]], dict[str, object]]] = {
    "trend_following": score_trend_following,
    "rotation_alpha": score_rotation_alpha,
    "mean_reversion": score_mean_reversion,
    "defensive_quality": score_defensive_quality,
}


def _latest_date(frame: pd.DataFrame, requested_as_of: str) -> str | None:
    if frame.empty:
        return None
    dates = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    dates = dates[dates <= requested_as_of]
    return str(dates.max()) if not dates.empty else None


def _latest_common_as_of(histories: Mapping[str, pd.DataFrame], benchmark: pd.DataFrame, requested_as_of: str) -> str:
    latest_dates = [_latest_date(frame, requested_as_of) for frame in histories.values()]
    latest_dates.append(_latest_date(benchmark, requested_as_of))
    valid = [date for date in latest_dates if date]
    if len(valid) != len(latest_dates):
        raise ValueError("Missing histories for alpha model snapshot.")
    return min(valid)


def _price_frame(frame: pd.DataFrame, as_of: str) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return pd.DataFrame(columns=["trade_date", "close"])
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = result.dropna(subset=["trade_date", "close"])
    return result[result["trade_date"] <= as_of][["trade_date", "close"]].sort_values("trade_date").reset_index(drop=True)


def _drawdown_control(frame: pd.DataFrame, as_of: str, sessions: int = 252) -> float:
    clean = _price_frame(frame, as_of).tail(sessions)
    if clean.empty:
        return 50.0
    close = clean["close"].astype(float)
    running_max = close.cummax()
    drawdown = close / running_max - 1.0
    max_drawdown = abs(float(drawdown.min()))
    return round(max(0.0, min(100.0, (1.0 - max_drawdown / 0.45) * 100.0)), 4)


def _safe_number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(number):
        return default
    return number


def _feature_rows(mappings, histories: Mapping[str, pd.DataFrame], benchmark: pd.DataFrame, as_of: str) -> list[dict[str, object]]:
    metrics = {
        mapping.asset_code: compute_asset_metrics(mapping.asset_code, histories[mapping.asset_code], benchmark, as_of=as_of)
        for mapping in mappings
    }
    return20_scores = percentile_scores({code: item.get("return_20d") for code, item in metrics.items()})
    return60_scores = percentile_scores({code: item.get("return_60d") for code, item in metrics.items()})
    relative_scores = percentile_scores({code: item.get("relative_60d") for code, item in metrics.items()})
    risk_scores = percentile_scores({code: item.get("risk_adjusted_raw") for code, item in metrics.items()})
    volatility_scores = percentile_scores({code: item.get("volatility_60d") for code, item in metrics.items()})
    persistence = persistence_scores(histories, as_of=as_of)
    rows: list[dict[str, object]] = []
    for mapping in mappings:
        code = mapping.asset_code
        item = metrics[code]
        momentum = 0.45 * return20_scores[code] + 0.55 * return60_scores[code]
        trend = item.get("trend") if isinstance(item.get("trend"), Mapping) else {}
        penalty = extension_penalty(item)
        rows.append(
            {
                "code": code,
                "name": mapping.asset_name,
                "category": mapping.asset_category,
                "mapping_method": mapping.mapping_method,
                "research_source": (
                    mapping.research_proxy.code if mapping.research_proxy is not None else mapping.asset_code
                ),
                "return20_score": round(return20_scores[code], 4),
                "return60_score": round(return60_scores[code], 4),
                "momentum": round(momentum, 4),
                "relative_strength": round(relative_scores[code], 4),
                "trend_quality": round(_safe_number(trend.get("score")), 4),
                "risk_adjusted": round(risk_scores[code], 4),
                "persistence": round(float(persistence.get(code, 50.0)), 4),
                "extension_penalty": penalty,
                "price_percentile_252": round(_safe_number(item.get("price_percentile_252"), 0.5), 6),
                "deviation_ma120": round(_safe_number(item.get("deviation_ma120")), 6),
                "low_volatility": round(100.0 - volatility_scores[code], 4),
                "drawdown_control": _drawdown_control(histories[code], as_of),
                "metrics": {
                    "return_20d": item.get("return_20d"),
                    "return_60d": item.get("return_60d"),
                    "relative_60d": item.get("relative_60d"),
                    "volatility_60d": item.get("volatility_60d"),
                },
            }
        )
    return rows


def build_alpha_model_snapshot(
    date: str | int = "20991231",
    *,
    start_date: str | int = "20150105",
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
) -> dict[str, object]:
    requested_as_of = normalize_trade_date(date)
    start = normalize_trade_date(start_date)
    decision = build_alpha_regime_decision(requested_as_of)
    model_name = str(decision["recommended_model"])
    model = MODEL_DISPATCH[model_name]
    mappings = [mapping for mapping in read_asset_proxy_registry(registry_path) if mapping.enabled]
    histories = {
        mapping.asset_code: load_research_proxy_history(mapping, start, requested_as_of, cache_only=True)
        for mapping in mappings
    }
    benchmark = read_benchmark_cache(DEFAULT_BENCHMARK, start, requested_as_of)
    resolved_as_of = _latest_common_as_of(histories, benchmark, requested_as_of)
    rows = []
    for features in _feature_rows(mappings, histories, benchmark, resolved_as_of):
        scored = model(features)
        rows.append(
            {
                "code": features["code"],
                "name": features["name"],
                "category": features["category"],
                "mapping_method": features["mapping_method"],
                "research_source": features["research_source"],
                **scored,
                "feature_snapshot": {
                    key: features[key]
                    for key in (
                        "momentum",
                        "relative_strength",
                        "trend_quality",
                        "risk_adjusted",
                        "persistence",
                        "extension_penalty",
                        "price_percentile_252",
                        "deviation_ma120",
                        "low_volatility",
                        "drawdown_control",
                    )
                },
            }
        )
    ranked = rank_opportunities([{**row, "score": row["model_score"]} for row in rows])
    for row in ranked:
        row["model_score"] = row.pop("score")
    return {
        "metadata": {
            "engine": "V3.3.2 Regime-Specific Alpha Model Foundation",
            "requested_as_of": requested_as_of,
            "as_of": resolved_as_of,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "asset_count": len(ranked),
            "model": model_name,
            "alpha_regime": decision["alpha_regime"],
            "formula_stage": "model-specific research score; no allocation",
        },
        "router_decision": decision,
        "summary": {
            "top_assets": [
                {"rank": row["rank"], "code": row["code"], "name": row["name"], "model_score": row["model_score"]}
                for row in ranked[:5]
            ],
            "source_methods": dict(Counter(row["mapping_method"] for row in ranked)),
        },
        "assets": ranked,
        "constraints": {
            "router_driven_model": True,
            "does_not_change_v3_2_score": True,
            "no_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_backtest": True,
            "no_parameter_optimization": True,
        },
    }


def write_alpha_model_snapshot(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
