from __future__ import annotations

from typing import Mapping

import pandas as pd

from industry_structure.industry_loader import IndustryAsset
from industry_structure.industry_strength_engine import trailing_return


def _evaluation_dates(frames: Mapping[str, pd.DataFrame], as_of: str, limit: int = 60) -> list[str]:
    dates: set[str] = set()
    for frame in frames.values():
        if frame.empty:
            continue
        series = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
        dates.update(str(item) for item in series[series <= as_of].tail(limit + 80))
    return sorted(date for date in dates if date <= as_of)[-limit:]


def _rank_table_for_date(
    frames: Mapping[str, pd.DataFrame],
    eval_date: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for code, frame in frames.items():
        ret20 = trailing_return(frame, eval_date, 20)
        ret60 = trailing_return(frame, eval_date, 60)
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


def build_theme_persistence(
    assets: Mapping[str, IndustryAsset],
    frames: Mapping[str, pd.DataFrame],
    as_of: str,
    *,
    lookback: int = 60,
) -> dict[str, object]:
    ranking_frames = [_rank_table_for_date(frames, date_text) for date_text in _evaluation_dates(frames, as_of, lookback)]
    ranking_frames = [frame for frame in ranking_frames if not frame.empty]
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
