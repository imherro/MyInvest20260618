from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from config import DATA_DIR
from core.data_loader import normalize_trade_date
from industry_structure.industry_loader import IndustryAsset, load_asset_history
from industry_structure.opportunity_engine import build_industry_opportunity_snapshot
from theme_risk.crowding_risk_engine import evaluate_crowding_risk
from theme_risk.valuation_pressure_engine import evaluate_valuation_pressure


DEFAULT_OUTPUT_PATH = DATA_DIR / "theme_risk_snapshot.json"


def _risk_level(crowding_score: float, quality_score: float) -> str:
    if crowding_score >= 72 or quality_score < 45:
        return "high"
    if crowding_score >= 48:
        return "medium"
    return "low"


def _warning_union(*groups: list[str]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for item in group:
            if item not in result:
                result.append(item)
    return result


def _load_theme_frames(
    themes: list[Mapping[str, object]],
    start_date: str,
    as_of: str,
    *,
    cache_only: bool,
) -> tuple[dict[str, object], dict[str, object]]:
    frames = {}
    errors: dict[str, str] = {}
    for theme in themes:
        code = str(theme.get("code"))
        if not code:
            continue
        asset = IndustryAsset(
            code=code,
            name=str(theme.get("name") or code),
            source_type=str(theme.get("source_type") or "industry_index"),
            source="theme_risk_input",
        )
        try:
            frame = load_asset_history(asset, start_date, as_of, cache_only=cache_only)
        except Exception as exc:
            errors[code] = str(exc)
            continue
        if frame.empty:
            errors[code] = "empty history"
            continue
        frames[code] = frame
    return frames, {"requested_codes": [str(theme.get("code")) for theme in themes], "available_count": len(frames), "errors": errors}


def build_theme_risk_snapshot(
    as_of: str | int,
    *,
    industry_payload: Mapping[str, object] | None = None,
    start_date: str | int = "20240101",
    cache_only: bool = True,
) -> dict[str, object]:
    requested_as_of = normalize_trade_date(as_of)
    start = normalize_trade_date(start_date)
    industry = industry_payload or build_industry_opportunity_snapshot(
        requested_as_of,
        start_date=start,
        cache_only=cache_only,
    )
    resolved_as_of = str(industry.get("as_of") or requested_as_of)
    top_themes = list(industry.get("top_themes") or [])
    frames, frame_status = _load_theme_frames(top_themes, start, resolved_as_of, cache_only=cache_only)
    valuation_items = evaluate_valuation_pressure(top_themes, frames, resolved_as_of)
    crowding = evaluate_crowding_risk(industry, valuation_items)
    opportunity_score = float(industry.get("industry_opportunity_score") or 0.0)
    theme_persistence = float(industry.get("theme_persistence") or 0.0)
    crowding_score = float(crowding["crowding_score"])
    quality_score = 0.45 * opportunity_score + 0.25 * theme_persistence + 0.30 * (100.0 - crowding_score)
    valuation_warnings = _warning_union(*[list(item.get("warnings") or []) for item in valuation_items])
    warnings = _warning_union(valuation_warnings, list(crowding.get("warnings") or []))
    risk_level = _risk_level(crowding_score, quality_score)
    top_theme = top_themes[0] if top_themes else {}
    return {
        "engine": "V2.3.4 Theme Valuation & Crowding Risk Layer",
        "requested_as_of": requested_as_of,
        "as_of": resolved_as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "theme_risk_level": risk_level,
        "quality_score": round(quality_score, 4),
        "crowding_score": round(crowding_score, 4),
        "top_theme": {
            "code": top_theme.get("code"),
            "name": top_theme.get("name"),
            "composite_score": top_theme.get("composite_score"),
        },
        "warnings": warnings,
        "valuation_pressure": valuation_items,
        "crowding": crowding,
        "input_summary": {
            "industry_opportunity_score": industry.get("industry_opportunity_score"),
            "industry_strength": industry.get("industry_strength"),
            "theme_persistence": industry.get("theme_persistence"),
            "industry_source_type": industry.get("source_type"),
            "top_theme_count": len(top_themes),
        },
        "data_quality": {
            "theme_frames": frame_status,
            "industry_as_of": industry.get("as_of"),
            "no_future_data": resolved_as_of <= requested_as_of,
            "valuation_is_price_position_proxy": True,
        },
        "explanation": [
            "本层只判断主线机会是否过热或拥挤，不改变 Structural Bull 状态。",
            "valuation_pressure 使用价格位置、均线偏离和短中期涨幅做代理，不是 PE/PB 等基本面估值。",
            f"当前风险等级 {risk_level}，quality_score={quality_score:.1f}，crowding_score={crowding_score:.1f}。",
            "V2.3.4 不输出仓位、ETF 配置、买卖建议或回测结论。",
        ],
        "constraints": {
            "does_not_change_structural_bull_state": True,
            "no_etf_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_backtest": True,
            "quality_filter_only": True,
        },
    }


def write_theme_risk_snapshot(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
