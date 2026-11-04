from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from asset_opportunity.asset_strength_engine import (
    compute_asset_metrics,
    extension_penalty,
    percentile_scores,
    persistence_scores,
)
from asset_opportunity.opportunity_explainer import explain_asset_opportunity
from asset_opportunity.opportunity_ranker import rank_opportunities
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date
from config import DATA_DIR
from theme_risk.opportunity_quality_engine import build_theme_risk_snapshot


DEFAULT_OUTPUT_PATH = DATA_DIR / "asset_opportunity_snapshot.json"
DEFAULT_BENCHMARK = "510300.SH"
WEIGHTS = {
    "momentum": 0.35,
    "relative_strength": 0.25,
    "trend_quality": 0.20,
    "risk_adjusted": 0.10,
    "persistence": 0.10,
}


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_theme_risk_payload(
    *,
    theme_risk_path: str | Path,
    as_of: str,
    cache_only: bool,
) -> tuple[dict[str, object], dict[str, object]]:
    cached = _read_json(Path(theme_risk_path))
    cached_as_of = str(cached.get("as_of") or "") if cached else ""
    if cached and cached_as_of and cached_as_of <= as_of:
        return cached, {"source": "cached_theme_risk_snapshot", "as_of": cached_as_of, "no_future_data": True}
    try:
        payload = build_theme_risk_snapshot(as_of, cache_only=cache_only)
    except Exception as exc:
        return {}, {
            "source": "disabled",
            "as_of": None,
            "no_future_data": True,
            "disabled_reason": f"theme risk unavailable at {as_of}: {exc}",
            "cached_as_of": cached_as_of or None,
            "cached_ignored_as_future": bool(cached_as_of and cached_as_of > as_of),
        }
    payload_as_of = str(payload.get("as_of") or "")
    if payload_as_of > as_of:
        return {}, {
            "source": "disabled",
            "as_of": payload_as_of,
            "no_future_data": False,
            "disabled_reason": f"theme risk resolved after opportunity as_of: {payload_as_of}>{as_of}",
            "cached_as_of": cached_as_of or None,
        }
    return payload, {"source": "rebuilt_read_only", "as_of": payload_as_of, "no_future_data": True}


def _latest_date(frame: pd.DataFrame, requested_as_of: str) -> str | None:
    if frame.empty:
        return None
    dates = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    dates = dates[dates <= requested_as_of]
    return str(dates.max()) if not dates.empty else None


def _latest_common_as_of(
    histories: Mapping[str, pd.DataFrame],
    benchmark: pd.DataFrame,
    requested_as_of: str,
) -> str:
    latest_dates = [_latest_date(frame, requested_as_of) for frame in histories.values()]
    latest_dates.append(_latest_date(benchmark, requested_as_of))
    valid = [date for date in latest_dates if date]
    if len(valid) != len(latest_dates):
        missing = [code for code, frame in histories.items() if _latest_date(frame, requested_as_of) is None]
        raise ValueError(f"Missing asset history for opportunity snapshot: {missing}")
    return min(valid)


def _source_payload(mapping) -> dict[str, object]:
    if mapping.research_proxy is None:
        return {
            "code": mapping.asset_code,
            "name": mapping.asset_name,
            "type": "etf",
            "method": "direct_etf_history_only",
            "research_only": False,
        }
    return {
        "code": mapping.research_proxy.code,
        "name": mapping.research_proxy.name,
        "type": mapping.research_proxy.type,
        "method": "research_only",
        "research_only": True,
    }


def _theme_pressure_by_code(theme_risk_payload: Mapping[str, object]) -> dict[str, float]:
    values: dict[str, float] = {}
    for item in theme_risk_payload.get("valuation_pressure") or []:
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("code") or "")
        if not code:
            continue
        try:
            values[code] = float(item.get("valuation_pressure_score") or 0.0)
        except (TypeError, ValueError):
            values[code] = 0.0
    return values


def crowding_penalty(mapping, theme_risk_payload: Mapping[str, object]) -> float:
    if mapping.research_proxy is None:
        return 0.0
    pressure = _theme_pressure_by_code(theme_risk_payload).get(mapping.research_proxy.code, 0.0)
    try:
        global_crowding = float(theme_risk_payload.get("crowding_score") or 0.0)
    except (TypeError, ValueError):
        global_crowding = 0.0
    risk_level = str(theme_risk_payload.get("theme_risk_level") or "unknown")
    level_penalty = {"high": 5.0, "medium": 2.5, "low": 0.0}.get(risk_level, 0.0)
    return round(min(18.0, 0.12 * pressure + 0.03 * max(0.0, global_crowding - 50.0) + level_penalty), 4)


def _round_metrics(metrics: Mapping[str, object]) -> dict[str, object]:
    rounded: dict[str, object] = {}
    for key, value in metrics.items():
        if isinstance(value, float):
            rounded[key] = round(value, 6)
        elif isinstance(value, Mapping):
            rounded[key] = {
                nested_key: round(nested_value, 6) if isinstance(nested_value, float) else nested_value
                for nested_key, nested_value in value.items()
            }
        else:
            rounded[key] = value
    return rounded


def _component_payload(value: float) -> float:
    return round(float(value), 4)


def build_asset_opportunity_snapshot(
    as_of: str | int = "20991231",
    *,
    start_date: str | int = "20150105",
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    theme_risk_path: str | Path = DATA_DIR / "theme_risk_snapshot.json",
    cache_only: bool = True,
) -> dict[str, object]:
    requested_as_of = normalize_trade_date(as_of)
    start = normalize_trade_date(start_date)
    mappings = [mapping for mapping in read_asset_proxy_registry(registry_path) if mapping.enabled]
    histories = {
        mapping.asset_code: load_research_proxy_history(mapping, start, requested_as_of, cache_only=cache_only)
        for mapping in mappings
    }
    benchmark = read_benchmark_cache(DEFAULT_BENCHMARK, start, requested_as_of)
    resolved_as_of = _latest_common_as_of(histories, benchmark, requested_as_of)
    raw_metrics = {
        mapping.asset_code: compute_asset_metrics(mapping.asset_code, histories[mapping.asset_code], benchmark, as_of=resolved_as_of)
        for mapping in mappings
    }
    return20_scores = percentile_scores({code: item.get("return_20d") for code, item in raw_metrics.items()})
    return60_scores = percentile_scores({code: item.get("return_60d") for code, item in raw_metrics.items()})
    relative_scores = percentile_scores({code: item.get("relative_60d") for code, item in raw_metrics.items()})
    risk_scores = percentile_scores({code: item.get("risk_adjusted_raw") for code, item in raw_metrics.items()})
    persistence = persistence_scores(histories, as_of=resolved_as_of)
    theme_risk, theme_risk_status = _load_theme_risk_payload(
        theme_risk_path=theme_risk_path,
        as_of=resolved_as_of,
        cache_only=cache_only,
    )
    rows: list[dict[str, object]] = []
    for mapping in mappings:
        code = mapping.asset_code
        metrics = raw_metrics[code]
        momentum = 0.45 * return20_scores[code] + 0.55 * return60_scores[code]
        trend_quality = float((metrics.get("trend") or {}).get("score") or 0.0)
        components = {
            "momentum": _component_payload(momentum),
            "relative_strength": _component_payload(relative_scores[code]),
            "trend_quality": _component_payload(trend_quality),
            "risk_adjusted": _component_payload(risk_scores[code]),
            "persistence": _component_payload(persistence.get(code, 50.0)),
        }
        strength = sum(components[key] * weight for key, weight in WEIGHTS.items())
        penalty = {
            "extension": extension_penalty(metrics),
            "crowding": crowding_penalty(mapping, theme_risk),
        }
        score = max(0.0, min(100.0, strength - penalty["extension"] - penalty["crowding"]))
        row = {
            "code": mapping.asset_code,
            "name": mapping.asset_name,
            "category": mapping.asset_category,
            "mapping_method": mapping.mapping_method,
            "research_source": _source_payload(mapping),
            "score": round(score, 4),
            "strength": round(strength, 4),
            "components": components,
            "penalty": penalty,
            "metrics": _round_metrics(metrics),
            "constraints": {
                "no_allocation": True,
                "no_trade": True,
                "no_backtest": True,
                "research_proxy_does_not_create_tradable_history": mapping.research_proxy is not None,
            },
        }
        row["explanation"] = explain_asset_opportunity(row)
        rows.append(row)
    ranked = rank_opportunities(rows)
    source_methods = Counter(row["mapping_method"] for row in ranked)
    return {
        "metadata": {
            "engine": "V3.2.1 Asset Opportunity Score Engine",
            "requested_as_of": requested_as_of,
            "as_of": resolved_as_of,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "asset_count": len(ranked),
            "benchmark": DEFAULT_BENCHMARK,
            "formula": {
                "strength": WEIGHTS,
                "score": "strength - extension_penalty - crowding_penalty",
                "fixed_parameters": True,
                "no_parameter_optimization": True,
            },
            "purpose": "Asset opportunity scoring and ranking only; no allocation, no position sizing, no backtest.",
        },
        "summary": {
            "top_assets": [
                {"rank": row["rank"], "code": row["code"], "name": row["name"], "score": row["score"]}
                for row in ranked[:5]
            ],
            "source_methods": dict(source_methods),
            "proxy_usage_ratio": round(source_methods.get("research_only", 0) / len(ranked), 4) if ranked else 0.0,
            "theme_risk_as_of": theme_risk.get("as_of"),
            "theme_risk_level": theme_risk.get("theme_risk_level"),
        },
        "assets": ranked,
        "data_quality": {
            "start_date": start,
            "requested_as_of": requested_as_of,
            "as_of": resolved_as_of,
            "no_future_data": resolved_as_of <= requested_as_of,
            "uses_research_proxy_for_research_only": True,
            "theme_risk_loaded": bool(theme_risk),
            "theme_risk_status": theme_risk_status,
        },
        "constraints": {
            "etf_and_proxy_separated": True,
            "no_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_backtest": True,
            "does_not_modify_v2": True,
        },
    }


def write_asset_opportunity_snapshot(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
