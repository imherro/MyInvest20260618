from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from config import DATA_DIR, DEFAULT_INDEX_CODE
from core.data_loader import cache_path_for, normalize_trade_date
from industry_structure.industry_loader import IndustryAsset, load_industry_panel
from theme_risk.crowding_risk_engine import evaluate_crowding_risk
from theme_risk.valuation_pressure_engine import evaluate_valuation_pressure


DEFAULT_OUTPUT_PATH = DATA_DIR / "historical_style_context.json"
DEFAULT_COVERAGE_OUTPUT_PATH = DATA_DIR / "historical_style_context_coverage.json"
DEFAULT_BENCHMARK_CODES = ("000300.SH", "000905.SH")
MARKET_FEATURE_FIELDS = (
    "trend",
    "breadth",
    "liquidity",
    "volatility",
    "pressure",
)
STYLE_CONTEXT_FIELDS = (
    "industry_breadth",
    "positive_industry_ratio",
    "top_industry_ratio",
    "theme_persistence",
    "crowding_score",
    "price_extension",
    "theme_risk_level",
    *MARKET_FEATURE_FIELDS,
)


def _read_index_cache(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    path = cache_path_for(ts_code)
    if not path.exists():
        raise FileNotFoundError(f"index cache missing for {ts_code}: {path}")
    df = pd.read_csv(path, dtype={"trade_date": str})
    df["trade_date"] = df["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result = df[(df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)].copy()
    return result.sort_values("trade_date").reset_index(drop=True)


def _read_structural_rows(path: str | Path = DATA_DIR / "structural_hazard_dataset.json") -> list[dict[str, object]]:
    source = Path(path)
    if not source.exists():
        return []
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return sorted((dict(row) for row in payload if isinstance(row, Mapping)), key=lambda row: str(row.get("date")))


def _structural_row_for_date(rows: list[Mapping[str, object]], date_text: str) -> Mapping[str, object] | None:
    result = None
    for row in rows:
        row_date = str(row.get("date") or "")
        if row_date > date_text:
            break
        result = row
    return result


def _evaluation_dates(start_date: str, end_date: str, step_sessions: int) -> list[str]:
    benchmark = _read_index_cache(DEFAULT_INDEX_CODE, start_date, end_date)
    dates = benchmark["trade_date"].astype(str).tolist()
    if not dates:
        return []
    sampled = dates[::max(1, int(step_sessions))]
    if sampled[-1] != dates[-1]:
        sampled.append(dates[-1])
    return sampled


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
                "name": str(item.get("name") or code),
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


def _risk_level(crowding_score: float, quality_score: float) -> str:
    if crowding_score >= 72 or quality_score < 45:
        return "high"
    if crowding_score >= 48:
        return "medium"
    return "low"


def _prepare_price_cache(frames: Mapping[str, pd.DataFrame]) -> dict[str, dict[str, list[object]]]:
    cache: dict[str, dict[str, list[object]]] = {}
    for code, frame in frames.items():
        if frame.empty:
            continue
        df = frame.copy()
        df["trade_date"] = df["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)
        if df.empty:
            continue
        cache[str(code)] = {
            "dates": df["trade_date"].astype(str).tolist(),
            "close": [float(value) for value in df["close"].tolist()],
        }
    return cache


def _last_index_on_or_before(dates: list[str], as_of: str) -> int:
    index = -1
    for idx, date_text in enumerate(dates):
        if date_text > as_of:
            break
        index = idx
    return index


def _trailing_return_cached(price_row: Mapping[str, list[object]], as_of: str, window: int) -> float | None:
    dates = [str(value) for value in price_row.get("dates") or []]
    close = [float(value) for value in price_row.get("close") or []]
    index = _last_index_on_or_before(dates, as_of)
    if index < window:
        return None
    previous = close[index - window]
    if previous <= 0:
        return None
    return close[index] / previous - 1.0


def _rank_percent(values: pd.Series) -> pd.Series:
    if values.empty:
        return values
    return values.rank(method="average", pct=True) * 100.0


def _benchmark_returns_cached(price_cache: Mapping[str, Mapping[str, list[object]]], as_of: str) -> dict[str, object]:
    by_code: dict[str, dict[str, float | None]] = {}
    average: dict[str, float | None] = {}
    for code, row in price_cache.items():
        by_code[code] = {
            f"return_{window}d": _trailing_return_cached(row, as_of, window)
            for window in (5, 20, 60)
        }
    for window in (5, 20, 60):
        values = [
            float(metrics[f"return_{window}d"])
            for metrics in by_code.values()
            if metrics.get(f"return_{window}d") is not None
        ]
        average[f"return_{window}d"] = sum(values) / len(values) if values else None
    return {"by_code": by_code, "average": average}


def _build_industry_strength_cached(
    assets: Mapping[str, IndustryAsset],
    price_cache: Mapping[str, Mapping[str, list[object]]],
    benchmark_price_cache: Mapping[str, Mapping[str, list[object]]],
    as_of: str,
) -> dict[str, object]:
    benchmark = _benchmark_returns_cached(benchmark_price_cache, as_of)
    benchmark_average = benchmark["average"]
    rows: list[dict[str, object]] = []
    for code, price_row in price_cache.items():
        asset = assets.get(code)
        if asset is None:
            continue
        returns = {
            f"return_{window}d": _trailing_return_cached(price_row, as_of, window)
            for window in (5, 20, 60)
        }
        if returns["return_60d"] is None or returns["return_20d"] is None:
            continue
        relative_60d = None
        if benchmark_average.get("return_60d") is not None:
            relative_60d = float(returns["return_60d"]) - float(benchmark_average["return_60d"])
        rows.append(
            {
                "code": code,
                "name": asset.name,
                "source_type": asset.source_type,
                **returns,
                "relative_60d": relative_60d,
            }
        )

    table = pd.DataFrame(rows)
    if table.empty:
        return {
            "as_of": as_of,
            "benchmark_returns": benchmark,
            "industry_strength": 0.0,
            "industry_breadth": 0.0,
            "positive_industry_ratio": 0.0,
            "top_industry_ratio": 0.0,
            "rotation_health": 0.0,
            "industries": [],
        }

    for column in ["return_5d", "return_20d", "return_60d", "relative_60d"]:
        table[f"{column}_rank"] = _rank_percent(pd.to_numeric(table[column], errors="coerce"))

    table["strength_score"] = (
        0.18 * table["return_5d_rank"].fillna(50.0)
        + 0.32 * table["return_20d_rank"].fillna(50.0)
        + 0.32 * table["return_60d_rank"].fillna(50.0)
        + 0.18 * table["relative_60d_rank"].fillna(50.0)
    )
    table = table.sort_values("strength_score", ascending=False).reset_index(drop=True)
    industry_count = len(table)
    top_count = min(5, industry_count)
    positive_ratio = float((pd.to_numeric(table["return_20d"], errors="coerce") > 0).mean())
    top_ratio = float((table["strength_score"] >= 70.0).mean())
    industry_breadth = float(
        (
            (pd.to_numeric(table["return_20d"], errors="coerce") > 0)
            & (pd.to_numeric(table["return_60d"], errors="coerce") > 0)
        ).mean()
    )
    top_avg = float(table.head(top_count)["strength_score"].mean())
    rotation_health = 0.50 * top_avg + 0.30 * positive_ratio * 100.0 + 0.20 * top_ratio * 100.0
    industry_strength = 0.62 * top_avg + 0.23 * industry_breadth * 100.0 + 0.15 * top_ratio * 100.0

    industries = []
    for _, row in table.iterrows():
        industries.append(
            {
                "code": str(row["code"]),
                "name": str(row["name"]),
                "source_type": str(row["source_type"]),
                "return_5d": None if pd.isna(row["return_5d"]) else round(float(row["return_5d"]), 6),
                "return_20d": None if pd.isna(row["return_20d"]) else round(float(row["return_20d"]), 6),
                "return_60d": None if pd.isna(row["return_60d"]) else round(float(row["return_60d"]), 6),
                "relative_60d": None if pd.isna(row["relative_60d"]) else round(float(row["relative_60d"]), 6),
                "rank_percentile": round(float(row["strength_score"]), 4),
                "strength_score": round(float(row["strength_score"]), 4),
            }
        )

    return {
        "as_of": as_of,
        "benchmark_returns": benchmark,
        "industry_strength": round(industry_strength, 4),
        "industry_breadth": round(industry_breadth, 4),
        "positive_industry_ratio": round(positive_ratio, 4),
        "top_industry_ratio": round(top_ratio, 4),
        "rotation_health": round(rotation_health, 4),
        "industries": industries,
    }


def _persistence_evaluation_dates(price_cache: Mapping[str, Mapping[str, list[object]]], as_of: str, limit: int = 60) -> list[str]:
    dates: set[str] = set()
    for row in price_cache.values():
        series = [str(value) for value in row.get("dates") or []]
        available = [date for date in series if date <= as_of]
        dates.update(available[-(limit + 80):])
    return sorted(date for date in dates if date <= as_of)[-limit:]


def _rank_table_for_date_cached(
    price_cache: Mapping[str, Mapping[str, list[object]]],
    eval_date: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for code, price_row in price_cache.items():
        ret20 = _trailing_return_cached(price_row, eval_date, 20)
        ret60 = _trailing_return_cached(price_row, eval_date, 60)
        if ret20 is None or ret60 is None:
            continue
        rows.append({"code": code, "return_20d": ret20, "return_60d": ret60})
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["rank20"] = table["return_20d"].rank(method="average", pct=True) * 100.0
    table["rank60"] = table["return_60d"].rank(method="average", pct=True) * 100.0
    table["rank_score"] = 0.45 * table["rank20"] + 0.55 * table["rank60"]
    table["eval_date"] = eval_date
    return table


def _build_cached_theme_persistence(
    assets: Mapping[str, IndustryAsset],
    price_cache: Mapping[str, Mapping[str, list[object]]],
    as_of: str,
    rank_cache: dict[str, pd.DataFrame],
    *,
    lookback: int = 60,
) -> dict[str, object]:
    ranking_frames = []
    for date_text in _persistence_evaluation_dates(price_cache, as_of, lookback):
        if date_text not in rank_cache:
            rank_cache[date_text] = _rank_table_for_date_cached(price_cache, date_text)
        frame = rank_cache[date_text]
        if not frame.empty:
            ranking_frames.append(frame)
    if not ranking_frames:
        return {
            "as_of": as_of,
            "theme_persistence_score": 0.0,
            "persistence_by_industry": [],
            "ranking_observations": 0,
        }

    ranks = pd.concat(ranking_frames, ignore_index=True).sort_values(["code", "eval_date"])
    rows: list[dict[str, object]] = []
    for code, group in ranks.groupby("code"):
        asset = assets.get(str(code))
        if asset is None:
            continue
        group = group.sort_values("eval_date")
        last20 = group.tail(20)
        last40 = group.tail(40)
        last60 = group.tail(60)
        top20 = float((last20["rank_score"] >= 80.0).mean()) if not last20.empty else 0.0
        top40 = float((last40["rank_score"] >= 80.0).mean()) if not last40.empty else 0.0
        top60 = float((last60["rank_score"] >= 80.0).mean()) if not last60.empty else 0.0
        avg_rank60 = float(last60["rank_score"].mean()) if not last60.empty else 0.0
        latest_rank = float(group["rank_score"].iloc[-1])
        persistence_score = (
            0.30 * top20 * 100.0
            + 0.25 * top40 * 100.0
            + 0.20 * top60 * 100.0
            + 0.15 * avg_rank60
            + 0.10 * latest_rank
        )
        rows.append(
            {
                "code": str(code),
                "name": asset.name,
                "source_type": asset.source_type,
                "latest_rank": round(latest_rank, 4),
                "top20_hit_ratio": round(top20, 4),
                "top40_hit_ratio": round(top40, 4),
                "top60_hit_ratio": round(top60, 4),
                "avg_rank60": round(avg_rank60, 4),
                "persistence_score": round(float(persistence_score), 4),
            }
        )

    rows = sorted(rows, key=lambda item: float(item["persistence_score"]), reverse=True)
    top_count = min(5, len(rows))
    persistence_score = sum(float(item["persistence_score"]) for item in rows[:top_count]) / top_count if top_count else 0.0
    return {
        "as_of": as_of,
        "theme_persistence_score": round(persistence_score, 4),
        "persistence_by_industry": rows,
        "ranking_observations": int(len(ranks)),
    }


def _float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _sanitize_local_paths(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _sanitize_local_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_local_paths(item) for item in value]
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        marker = "MyInvestCycle/"
        if marker in normalized:
            return normalized.split(marker, 1)[1]
    return value


def _context_for_date(
    *,
    date_text: str,
    assets: list[IndustryAsset],
    frames: Mapping[str, pd.DataFrame],
    price_cache: Mapping[str, Mapping[str, list[object]]],
    benchmark_price_cache: Mapping[str, Mapping[str, list[object]]],
    structural_rows: list[Mapping[str, object]],
    rank_cache: dict[str, pd.DataFrame],
) -> dict[str, object]:
    asset_map = {asset.code: asset for asset in assets}
    strength = _build_industry_strength_cached(asset_map, price_cache, benchmark_price_cache, date_text)
    persistence = _build_cached_theme_persistence(asset_map, price_cache, date_text, rank_cache)
    top_themes = _top_themes(
        list(strength.get("industries") or []),
        list(persistence.get("persistence_by_industry") or []),
    )
    industry_strength = float(strength.get("industry_strength") or 0.0)
    theme_persistence = float(persistence.get("theme_persistence_score") or 0.0)
    rotation_health = float(strength.get("rotation_health") or 0.0)
    industry_opportunity_score = 0.42 * industry_strength + 0.38 * theme_persistence + 0.20 * rotation_health
    industry_payload = {
        "industry_opportunity_score": round(industry_opportunity_score, 4),
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
    }
    valuation_items = evaluate_valuation_pressure(top_themes, frames, date_text)
    crowding = evaluate_crowding_risk(industry_payload, valuation_items)
    crowding_score = float(crowding["crowding_score"])
    quality_score = 0.45 * industry_opportunity_score + 0.25 * theme_persistence + 0.30 * (100.0 - crowding_score)
    structural_row = _structural_row_for_date(structural_rows, date_text)
    structural_features = (structural_row or {}).get("features") or {}
    style_context = {
        "industry_breadth": strength.get("industry_breadth"),
        "positive_industry_ratio": strength.get("positive_industry_ratio"),
        "top_industry_ratio": strength.get("top_industry_ratio"),
        "theme_persistence": round(theme_persistence, 4),
        "crowding_score": round(crowding_score, 4),
        "price_extension": crowding.get("average_top_theme_pressure"),
        "theme_risk_level": _risk_level(crowding_score, quality_score),
        "trend": _float(structural_features.get("trend")),
        "breadth": _float(structural_features.get("breadth")),
        "liquidity": _float(structural_features.get("liquidity")),
        "volatility": _float(structural_features.get("volatility")),
        "pressure": _float(structural_features.get("pressure")),
    }
    missing_fields = [field for field in STYLE_CONTEXT_FIELDS if style_context.get(field) is None]
    return {
        "date": date_text,
        "style_context": style_context,
        "top_themes": top_themes[:5],
        "source": "historical_reconstruction_from_local_cache",
        "future_safe": True,
        "data_quality": {
            "no_future_data": True,
            "industry_count": len(strength.get("industries") or []),
            "top_theme_count": len(top_themes),
            "valuation_item_count": len(valuation_items),
            "ranking_observations": persistence.get("ranking_observations"),
            "structural_features_available": structural_row is not None,
            "missing_fields": missing_fields,
        },
    }


def audit_style_context_coverage(payload: Mapping[str, object]) -> dict[str, object]:
    rows = [row for row in payload.get("rows") or [] if isinstance(row, Mapping)]
    total = len(rows)
    field_coverage = {}
    for field in STYLE_CONTEXT_FIELDS:
        available = sum(1 for row in rows if ((row.get("style_context") or {}).get(field) is not None))
        field_coverage[field] = {
            "available": available,
            "missing": total - available,
            "coverage_rate": None if total == 0 else round(available / total, 6),
        }
    dates = [str(row.get("date")) for row in rows if row.get("date")]
    full_rows = [
        row for row in rows
        if not (row.get("data_quality") or {}).get("missing_fields")
    ]
    return {
        "metadata": {
            "engine": "V3.5.5 Historical Style Context Coverage Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_engine": (payload.get("metadata") or {}).get("engine"),
            "requested_window": (payload.get("metadata") or {}).get("requested_window"),
            "row_count": total,
            "actual_start": min(dates) if dates else None,
            "actual_end": max(dates) if dates else None,
        },
        "summary": {
            "fully_populated_rows": len(full_rows),
            "fully_populated_rate": None if total == 0 else round(len(full_rows) / total, 6),
            "field_coverage": field_coverage,
            "known_limitations": [
                "Market structure fields before the first structural_hazard_dataset date are unavailable and remain null.",
                "Industry and theme context is reconstructed from local historical index caches only; no live refresh is performed.",
                "price_extension is a price-position proxy based on top theme valuation pressure, not fundamental valuation.",
            ],
        },
        "constraints": {
            "coverage_audit_only": True,
            "no_future_data": True,
            "no_model_change": True,
            "no_trade_signal": True,
            "no_allocation": True,
        },
    }


def build_historical_style_context(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    step_sessions: int = 20,
    cache_only: bool = True,
) -> dict[str, object]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    dates = _evaluation_dates(start, end, step_sessions)
    if not dates:
        raise ValueError("No benchmark dates available for historical style context.")
    assets, frames, industry_status = load_industry_panel(start, end, cache_only=cache_only)
    benchmark_frames = {
        code: _read_index_cache(code, start, end)
        for code in DEFAULT_BENCHMARK_CODES
    }
    price_cache = _prepare_price_cache(frames)
    benchmark_price_cache = _prepare_price_cache(benchmark_frames)
    structural_rows = _read_structural_rows()
    rank_cache: dict[str, pd.DataFrame] = {}
    rows = [
        _context_for_date(
            date_text=date_text,
            assets=assets,
            frames=frames,
            price_cache=price_cache,
            benchmark_price_cache=benchmark_price_cache,
            structural_rows=structural_rows,
            rank_cache=rank_cache,
        )
        for date_text in dates
    ]
    payload = {
        "metadata": {
            "engine": "V3.5.5 Historical Style Context Feature Expansion",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "requested_window": {"start": start, "end": end},
            "actual_window": {"start": rows[0]["date"], "end": rows[-1]["date"]},
            "step_sessions": step_sessions,
            "row_count": len(rows),
            "source": "local cache reconstruction",
            "industry_status": _sanitize_local_paths(industry_status),
            "benchmark_codes": list(DEFAULT_BENCHMARK_CODES),
        },
        "rows": rows,
        "coverage": {},
        "constraints": {
            "historical_context_only": True,
            "cache_only": cache_only,
            "future_safe": True,
            "no_future_data": True,
            "does_not_modify_style_preference": True,
            "does_not_modify_router": True,
            "does_not_modify_alpha_model": True,
            "no_retraining": True,
            "no_parameter_optimization": True,
            "no_style_weight": True,
            "no_etf_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
        },
    }
    payload["coverage"] = audit_style_context_coverage(payload)["summary"]
    return payload


def write_historical_style_context(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_style_context_coverage(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_COVERAGE_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
