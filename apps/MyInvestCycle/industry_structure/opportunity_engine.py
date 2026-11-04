from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from config import DATA_DIR
from core.data_loader import cache_path_for, get_index_daily, normalize_trade_date
from industry_structure.industry_loader import IndustryAsset, load_industry_panel
from industry_structure.industry_strength_engine import build_industry_strength
from industry_structure.theme_persistence_engine import build_theme_persistence


DEFAULT_BENCHMARK_CODES = ("000300.SH", "000905.SH")
DEFAULT_OUTPUT_PATH = DATA_DIR / "industry_opportunity_snapshot.json"


def _read_index_cache_only(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    path = cache_path_for(ts_code)
    if not path.exists():
        raise FileNotFoundError(f"index cache missing for {ts_code}: {path}")
    df = pd.read_csv(path, dtype={"trade_date": str})
    df["trade_date"] = df["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    return df[(df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)].sort_values("trade_date").reset_index(drop=True)


def _load_benchmarks(
    start_date: str,
    end_date: str,
    *,
    cache_only: bool,
    refresh: bool,
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for code in DEFAULT_BENCHMARK_CODES:
        try:
            if cache_only:
                frame = _read_index_cache_only(code, start_date, end_date)
            else:
                frame = get_index_daily(code, start_date, end_date, refresh=refresh)
        except Exception as exc:
            errors[code] = str(exc)
            continue
        if frame.empty:
            errors[code] = "empty history"
            continue
        frames[code] = frame
    return frames, {"benchmark_codes": list(DEFAULT_BENCHMARK_CODES), "available_count": len(frames), "errors": errors}


def _latest_common_as_of(
    requested_as_of: str,
    frames: Mapping[str, pd.DataFrame],
    benchmark_frames: Mapping[str, pd.DataFrame],
) -> str:
    latest_dates: list[str] = []
    for frame in [*frames.values(), *benchmark_frames.values()]:
        if frame.empty:
            continue
        dates = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
        dates = dates[dates <= requested_as_of]
        if not dates.empty:
            latest_dates.append(str(dates.max()))
    if not latest_dates:
        raise ValueError("No industry or benchmark data available on or before requested date.")
    return min(max(latest_dates), requested_as_of)


def _top_themes(
    strength_items: list[Mapping[str, object]],
    persistence_items: list[Mapping[str, object]],
    *,
    limit: int = 8,
) -> list[dict[str, object]]:
    persistence_by_code = {str(item["code"]): item for item in persistence_items}
    themes: list[dict[str, object]] = []
    for item in strength_items:
        code = str(item["code"])
        persistence = persistence_by_code.get(code, {})
        strength = float(item.get("strength_score") or 0.0)
        persistence_score = float(persistence.get("persistence_score") or 0.0)
        composite = 0.58 * strength + 0.42 * persistence_score
        themes.append(
            {
                "code": code,
                "name": str(item["name"]),
                "source_type": str(item.get("source_type") or ""),
                "strength": round(strength, 4),
                "persistence": round(persistence_score, 4),
                "composite_score": round(composite, 4),
                "return_20d": item.get("return_20d"),
                "return_60d": item.get("return_60d"),
                "relative_60d": item.get("relative_60d"),
            }
        )
    return sorted(themes, key=lambda row: float(row["composite_score"]), reverse=True)[:limit]


def _explain(snapshot: Mapping[str, object]) -> list[str]:
    source_type = str(snapshot.get("source_type"))
    score = float(snapshot.get("industry_opportunity_score") or 0.0)
    top = snapshot.get("top_themes") or []
    top_names = "、".join(str(item.get("name")) for item in top[:3]) if isinstance(top, list) else ""
    lines = [
        f"source_type={source_type}; 行业机会分只表示结构性赚钱效应强弱，不是买卖建议。",
        f"industry_opportunity_score={score:.1f}; 由行业强度、主线持续性和轮动健康度组合得到。",
    ]
    if top_names:
        lines.append(f"当前排名靠前的行业/主题是：{top_names}。")
    lines.append("V2.3.2 不输出仓位、不输出 ETF 配置、不输出交易信号、不做回测。")
    return lines


def build_industry_opportunity_snapshot(
    as_of: str | int,
    *,
    start_date: str | int = "20240101",
    refresh_universe: bool = False,
    refresh_prices: bool = False,
    cache_only: bool = False,
) -> dict[str, object]:
    requested_as_of = normalize_trade_date(as_of)
    start = normalize_trade_date(start_date)
    assets, frames, industry_status = load_industry_panel(
        start,
        requested_as_of,
        refresh_universe=refresh_universe,
        refresh_prices=refresh_prices,
        cache_only=cache_only,
    )
    benchmark_frames, benchmark_status = _load_benchmarks(
        start,
        requested_as_of,
        cache_only=cache_only,
        refresh=refresh_prices,
    )
    if not frames:
        raise ValueError("No industry histories available for opportunity snapshot.")
    if not benchmark_frames:
        raise ValueError("No benchmark histories available for opportunity snapshot.")

    resolved_as_of = _latest_common_as_of(requested_as_of, frames, benchmark_frames)
    asset_map = {asset.code: asset for asset in assets}
    strength = build_industry_strength(asset_map, frames, benchmark_frames, resolved_as_of)
    persistence = build_theme_persistence(asset_map, frames, resolved_as_of)
    top_themes = _top_themes(
        list(strength.get("industries") or []),
        list(persistence.get("persistence_by_industry") or []),
    )
    industry_strength = float(strength.get("industry_strength") or 0.0)
    theme_persistence = float(persistence.get("theme_persistence_score") or 0.0)
    rotation_health = float(strength.get("rotation_health") or 0.0)
    opportunity_score = 0.42 * industry_strength + 0.38 * theme_persistence + 0.20 * rotation_health
    source_type = str(industry_status.get("source_type") or "unknown")
    payload: dict[str, object] = {
        "engine": "V2.3.2 Industry / Theme Opportunity Engine",
        "requested_as_of": requested_as_of,
        "as_of": resolved_as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_type": source_type,
        "industry_opportunity_score": round(opportunity_score, 4),
        "industry_strength": round(industry_strength, 4),
        "theme_persistence": round(theme_persistence, 4),
        "top_themes": top_themes,
        "metrics": {
            "industry_breadth": strength.get("industry_breadth"),
            "positive_industry_ratio": strength.get("positive_industry_ratio"),
            "top_industry_ratio": strength.get("top_industry_ratio"),
            "rotation_health": strength.get("rotation_health"),
            "theme_persistence_score": persistence.get("theme_persistence_score"),
            "ranking_observations": persistence.get("ranking_observations"),
        },
        "benchmark_returns": strength.get("benchmark_returns"),
        "industries": strength.get("industries"),
        "persistence_by_industry": persistence.get("persistence_by_industry"),
        "data_quality": {
            "industry": industry_status,
            "benchmark": benchmark_status,
            "required_for_structural_bull_rotation": {
                "industry_strength": round(industry_strength, 4),
                "theme_persistence": round(theme_persistence, 4),
            },
            "no_future_data": resolved_as_of <= requested_as_of,
        },
        "constraints": {
            "no_etf_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_backtest": True,
            "industry_or_theme_research_only": True,
        },
    }
    payload["explanation"] = _explain(payload)
    return payload


def write_industry_opportunity_snapshot(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
