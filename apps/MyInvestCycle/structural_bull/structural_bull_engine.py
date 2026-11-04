from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from config import DATA_DIR
from core.data_loader import normalize_trade_date
from industry_structure.opportunity_engine import build_industry_opportunity_snapshot
from macro.macro_cycle_engine import build_macro_cycle_snapshot
from market_structure.structure_engine import build_structure_snapshot
from structural_bull.structural_bull_classifier import (
    classify_structural_bull,
    estimate_structural_confidence,
    score_structural_bull,
)
from structural_bull.structural_bull_explainer import explain_structural_bull


DEFAULT_OUTPUT_PATH = DATA_DIR / "structural_bull_snapshot.json"


def _num(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def _market_metrics(structure_payload: Mapping[str, object]) -> Mapping[str, object]:
    metrics = structure_payload.get("metrics")
    return metrics if isinstance(metrics, Mapping) else {}


def _industry_metrics(industry_payload: Mapping[str, object]) -> Mapping[str, object]:
    metrics = industry_payload.get("metrics")
    return metrics if isinstance(metrics, Mapping) else {}


def _layer_payload(
    macro_payload: Mapping[str, object],
    structure_payload: Mapping[str, object],
    industry_payload: Mapping[str, object],
) -> dict[str, object]:
    structure_metrics = _market_metrics(structure_payload)
    industry_metrics = _industry_metrics(industry_payload)
    return {
        "macro": {
            "state": macro_payload.get("macro_state"),
            "score": macro_payload.get("macro_score"),
            "confidence": macro_payload.get("confidence"),
            "as_of": macro_payload.get("as_of"),
        },
        "market_structure": {
            "state": structure_payload.get("structure_state"),
            "score": structure_payload.get("structure_score"),
            "confidence": structure_payload.get("confidence"),
            "as_of": structure_payload.get("as_of"),
            "index_trend": structure_metrics.get("index_trend"),
            "breadth": structure_metrics.get("breadth"),
            "liquidity": structure_metrics.get("liquidity"),
        },
        "industry_opportunity": {
            "state": "INDUSTRY_OPPORTUNITY",
            "score": industry_payload.get("industry_opportunity_score"),
            "as_of": industry_payload.get("as_of"),
            "source_type": industry_payload.get("source_type"),
            "industry_strength": industry_payload.get("industry_strength"),
            "theme_persistence": industry_payload.get("theme_persistence"),
            "rotation_health": industry_metrics.get("rotation_health"),
            "industry_breadth": industry_metrics.get("industry_breadth"),
            "top_industry_ratio": industry_metrics.get("top_industry_ratio"),
            "top_themes": industry_payload.get("top_themes") or [],
        },
    }


def _resolved_as_of(layer_payload: Mapping[str, object], requested_as_of: str) -> str:
    dates: list[str] = []
    for key in ("macro", "market_structure", "industry_opportunity"):
        item = layer_payload.get(key)
        if isinstance(item, Mapping) and item.get("as_of"):
            dates.append(str(item["as_of"]))
    market_dates = [date for date in dates if date <= requested_as_of]
    if not market_dates:
        return requested_as_of
    return min(market_dates)


def build_structural_bull_snapshot(
    as_of: str | int,
    *,
    macro_payload: Mapping[str, object] | None = None,
    structure_payload: Mapping[str, object] | None = None,
    industry_payload: Mapping[str, object] | None = None,
    macro_start_date: str | int = "20240101",
    structure_start_date: str | int = "20150101",
    industry_start_date: str | int = "20240101",
    history_sample_size: int = 30,
    cache_only: bool = True,
) -> dict[str, object]:
    requested_as_of = normalize_trade_date(as_of)
    macro = macro_payload or build_macro_cycle_snapshot(requested_as_of, start_date=str(macro_start_date))
    structure = structure_payload or build_structure_snapshot(
        requested_as_of,
        start_date=structure_start_date,
        history_sample_size=history_sample_size,
        cache_only=cache_only,
    )
    industry = industry_payload or build_industry_opportunity_snapshot(
        requested_as_of,
        start_date=industry_start_date,
        cache_only=cache_only,
    )
    layers = _layer_payload(macro, structure, industry)
    state = classify_structural_bull(layers)
    score = score_structural_bull(layers)
    confidence = estimate_structural_confidence(layers, state)
    return {
        "engine": "V2.3.3 Structural Bull Rotation Detector",
        "requested_as_of": requested_as_of,
        "as_of": _resolved_as_of(layers, requested_as_of),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "structural_state": state,
        "score": score,
        "confidence": confidence,
        "evidence": layers,
        "source_snapshots": {
            "macro_engine": macro.get("engine"),
            "market_structure_engine": structure.get("engine"),
            "industry_opportunity_engine": industry.get("engine"),
        },
        "data_quality": {
            "macro_as_of": layers["macro"].get("as_of"),
            "market_structure_as_of": layers["market_structure"].get("as_of"),
            "industry_opportunity_as_of": layers["industry_opportunity"].get("as_of"),
            "industry_source_type": layers["industry_opportunity"].get("source_type"),
            "no_future_data": _resolved_as_of(layers, requested_as_of) <= requested_as_of,
        },
        "thresholds": {
            "structural_bull_rotation": {
                "macro_not_bear": True,
                "market_structure_not_breakdown": True,
                "industry_strength_min": 52,
                "theme_persistence_min": 70,
                "rotation_health_min": 50,
                "top_industry_ratio_min": 0.12,
            }
        },
        "explanation": explain_structural_bull(state, layers),
        "constraints": {
            "no_etf_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_backtest": True,
            "state_and_evidence_only": True,
        },
    }


def write_structural_bull_snapshot(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
