from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Mapping

from config import DATA_DIR
from style_allocation.style_schema import STYLE_IDS, empty_style_scores, style_for_asset_code, style_for_bucket


def read_artifact(file_name: str, data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    path = Path(data_dir) / file_name
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _asset_opportunity_by_style(asset_opportunity: Mapping[str, object]) -> dict[str, object]:
    rows = asset_opportunity.get("assets") or []
    grouped: dict[str, list[dict[str, object]]] = {style_id: [] for style_id in STYLE_IDS}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        style_id = style_for_asset_code(str(row.get("code", "")))
        if style_id is None:
            continue
        grouped[style_id].append(
            {
                "code": str(row.get("code")),
                "name": str(row.get("name")),
                "rank": int(row.get("rank") or 0),
                "score": round(_float(row.get("score")), 4),
                "strength": round(_float(row.get("strength")), 4),
                "penalty": row.get("penalty") or {},
            }
        )

    result: dict[str, object] = {}
    for style_id, items in grouped.items():
        ranked = sorted(items, key=lambda item: int(item["rank"]) if int(item["rank"]) > 0 else 9999)
        scores = [float(item["score"]) for item in ranked]
        result[style_id] = {
            "asset_count": len(ranked),
            "average_score": None if not scores else round(mean(scores), 4),
            "best_score": None if not scores else round(max(scores), 4),
            "best_rank": None if not ranked else ranked[0]["rank"],
            "top_assets": ranked[:3],
        }
    return result


def _latest_alpha_exposure(robustness: Mapping[str, object]) -> dict[str, float]:
    latest = ((robustness.get("style_exposure") or {}).get("latest_exposure") or {})
    exposure = latest.get("exposure") or {}
    scores = empty_style_scores()
    if not isinstance(exposure, Mapping):
        return scores
    for bucket, share in exposure.items():
        style_id = style_for_bucket(str(bucket))
        if style_id is not None:
            scores[style_id] += _float(share)
    return {style_id: round(scores[style_id], 6) for style_id in STYLE_IDS}


def _residual_summary(residual_alpha: Mapping[str, object]) -> dict[str, object]:
    summary = residual_alpha.get("summary") or {}
    return {
        "economic_strength": summary.get("economic_strength"),
        "economically_meaningful_periods": summary.get("economically_meaningful_residual_alpha_periods") or [],
        "residual_alpha_persistent": bool(summary.get("residual_alpha_persistent")),
        "residual_cagr_by_period": summary.get("residual_cagr_by_period") or {},
        "interpretation": summary.get("interpretation"),
    }


def extract_style_allocation_inputs(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    macro = read_artifact("macro_cycle_snapshot.json", data_dir)
    structural = read_artifact("structural_bull_snapshot.json", data_dir)
    theme_risk = read_artifact("theme_risk_snapshot.json", data_dir)
    asset_opportunity = read_artifact("asset_opportunity_snapshot.json", data_dir)
    robustness = read_artifact("alpha_robustness_validation.json", data_dir)
    residual_alpha = read_artifact("residual_alpha_analysis.json", data_dir)

    structural_evidence = structural.get("evidence") or {}
    market_structure = structural_evidence.get("market_structure") or {}
    industry_opportunity = structural_evidence.get("industry_opportunity") or {}

    return {
        "as_of": structural.get("as_of") or macro.get("as_of") or asset_opportunity.get("metadata", {}).get("as_of"),
        "generated_sources": {
            "macro_cycle": {
                "engine": macro.get("engine"),
                "as_of": macro.get("as_of"),
                "macro_state": macro.get("macro_state"),
                "macro_score": macro.get("macro_score"),
                "confidence": macro.get("confidence"),
            },
            "structural_bull": {
                "engine": structural.get("engine"),
                "as_of": structural.get("as_of"),
                "structural_state": structural.get("structural_state"),
                "score": structural.get("score"),
                "confidence": structural.get("confidence"),
            },
            "theme_risk": {
                "engine": theme_risk.get("engine"),
                "as_of": theme_risk.get("as_of"),
                "theme_risk_level": theme_risk.get("theme_risk_level"),
                "quality_score": theme_risk.get("quality_score"),
                "crowding_score": theme_risk.get("crowding_score"),
                "warnings": theme_risk.get("warnings") or [],
            },
            "asset_opportunity": {
                "engine": (asset_opportunity.get("metadata") or {}).get("engine"),
                "as_of": (asset_opportunity.get("metadata") or {}).get("as_of"),
            },
            "alpha_robustness": {
                "engine": (robustness.get("metadata") or {}).get("engine"),
                "as_of": ((robustness.get("metadata") or {}).get("window") or {}).get("end"),
            },
            "residual_alpha": {
                "engine": (residual_alpha.get("metadata") or {}).get("engine"),
                "as_of": ((residual_alpha.get("metadata") or {}).get("window") or {}).get("end"),
            },
        },
        "macro": {
            "state": macro.get("macro_state"),
            "score": _float(macro.get("macro_score")),
            "confidence": _float(macro.get("confidence")),
        },
        "structural": {
            "state": structural.get("structural_state"),
            "score": _float(structural.get("score")),
            "confidence": _float(structural.get("confidence")),
        },
        "market_structure": {
            "state": market_structure.get("state"),
            "score": _float(market_structure.get("score")),
            "index_trend": _float(market_structure.get("index_trend")),
            "breadth": _float(market_structure.get("breadth")),
            "liquidity": _float(market_structure.get("liquidity")),
        },
        "industry_opportunity": {
            "state": industry_opportunity.get("state"),
            "score": _float(industry_opportunity.get("score")),
            "industry_strength": _float(industry_opportunity.get("industry_strength")),
            "theme_persistence": _float(industry_opportunity.get("theme_persistence")),
            "rotation_health": _float(industry_opportunity.get("rotation_health")),
            "industry_breadth": _float(industry_opportunity.get("industry_breadth")),
            "top_industry_ratio": _float(industry_opportunity.get("top_industry_ratio")),
            "top_themes": industry_opportunity.get("top_themes") or [],
        },
        "theme_risk": {
            "level": theme_risk.get("theme_risk_level"),
            "quality_score": _float(theme_risk.get("quality_score")),
            "crowding_score": _float(theme_risk.get("crowding_score")),
            "warnings": theme_risk.get("warnings") or [],
            "top_theme": theme_risk.get("top_theme") or {},
        },
        "asset_opportunity_by_style": _asset_opportunity_by_style(asset_opportunity),
        "latest_alpha_style_exposure": _latest_alpha_exposure(robustness),
        "residual_alpha": _residual_summary(residual_alpha),
    }
