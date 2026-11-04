from __future__ import annotations

from typing import Mapping

import pandas as pd

from industry_structure.industry_loader import IndustryAsset


WINDOWS = (5, 20, 60)


def _clean_frame(frame: pd.DataFrame, as_of: str) -> pd.DataFrame:
    df = frame.copy()
    df["trade_date"] = df["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["trade_date", "close"])
    df = df[df["trade_date"] <= as_of].sort_values("trade_date").reset_index(drop=True)
    return df


def trailing_return(frame: pd.DataFrame, as_of: str, window: int) -> float | None:
    df = _clean_frame(frame, as_of)
    if len(df) <= window:
        return None
    latest = float(df["close"].iloc[-1])
    previous = float(df["close"].iloc[-1 - window])
    if previous <= 0:
        return None
    return latest / previous - 1.0


def _benchmark_returns(benchmark_frames: Mapping[str, pd.DataFrame], as_of: str) -> dict[str, object]:
    by_code: dict[str, dict[str, float | None]] = {}
    average: dict[str, float | None] = {}
    for code, frame in benchmark_frames.items():
        by_code[code] = {
            f"return_{window}d": trailing_return(frame, as_of, window)
            for window in WINDOWS
        }
    for window in WINDOWS:
        values = [
            float(metrics[f"return_{window}d"])
            for metrics in by_code.values()
            if metrics.get(f"return_{window}d") is not None
        ]
        average[f"return_{window}d"] = sum(values) / len(values) if values else None
    return {"by_code": by_code, "average": average}


def _rank_percent(values: pd.Series) -> pd.Series:
    if values.empty:
        return values
    return values.rank(method="average", pct=True) * 100.0


def build_industry_strength(
    assets: Mapping[str, IndustryAsset],
    frames: Mapping[str, pd.DataFrame],
    benchmark_frames: Mapping[str, pd.DataFrame],
    as_of: str,
) -> dict[str, object]:
    benchmark = _benchmark_returns(benchmark_frames, as_of)
    benchmark_average = benchmark["average"]
    rows: list[dict[str, object]] = []
    for code, frame in frames.items():
        asset = assets.get(code)
        if asset is None:
            continue
        returns = {f"return_{window}d": trailing_return(frame, as_of, window) for window in WINDOWS}
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
