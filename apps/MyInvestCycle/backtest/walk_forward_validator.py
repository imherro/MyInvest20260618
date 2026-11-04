from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from config import CACHE_DIR


REQUIRED_SERIES = {
    "industry_opportunity_proxy": "index_daily_801080_SI.csv",
    "benchmark_510300": "fund_daily_510300_SH.csv",
    "benchmark_510500": "fund_daily_510500_SH.csv",
    "cash_proxy_511880": "fund_daily_511880_SH.csv",
}


def _range_for_cache(file_name: str) -> dict[str, object]:
    path = CACHE_DIR / file_name
    if not path.exists():
        return {"file": file_name, "available": False, "start": None, "end": None, "rows": 0}
    frame = pd.read_csv(path, dtype={"trade_date": str})
    if frame.empty or "trade_date" not in frame:
        return {"file": file_name, "available": False, "start": None, "end": None, "rows": 0}
    dates = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    return {
        "file": file_name,
        "available": True,
        "start": str(dates.min()),
        "end": str(dates.max()),
        "rows": int(len(frame)),
    }


def _max_start(items: Iterable[dict[str, object]]) -> str | None:
    starts = [str(item["start"]) for item in items if item.get("available") and item.get("start")]
    return max(starts) if starts else None


def _min_end(items: Iterable[dict[str, object]]) -> str | None:
    ends = [str(item["end"]) for item in items if item.get("available") and item.get("end")]
    return min(ends) if ends else None


def build_walk_forward_coverage_audit(
    *,
    desired_start: str = "20150101",
    desired_end: str = "20991231",
) -> dict[str, object]:
    series = {name: _range_for_cache(file_name) for name, file_name in REQUIRED_SERIES.items()}
    common_start = _max_start(series.values())
    common_end = _min_end(series.values())
    can_cover_desired = bool(common_start and common_end and common_start <= desired_start and common_end >= desired_end)
    blockers = []
    for name, item in series.items():
        if not item.get("available"):
            blockers.append(f"{name} cache missing")
            continue
        if item.get("start") and str(item["start"]) > desired_start:
            blockers.append(f"{name} starts at {item['start']}, later than desired {desired_start}")
        if item.get("end") and str(item["end"]) < desired_end:
            blockers.append(f"{name} ends at {item['end']}, earlier than desired {desired_end}")
    return {
        "desired_window": {"start": desired_start, "end": desired_end},
        "common_available_window": {"start": common_start, "end": common_end},
        "can_cover_desired_window": can_cover_desired,
        "series": series,
        "blockers": blockers,
        "policy": {
            "do_not_backfill_silently": True,
            "do_not_treat_partial_cache_as_full_history": True,
            "report_window_gap_in_web": True,
        },
    }
