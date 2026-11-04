"""Investable-universe filters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class UniverseFilterResult:
    frame: pd.DataFrame
    stats: dict[str, int]


def apply_universe_filters(stock_basic: pd.DataFrame, as_of: date | None = None) -> UniverseFilterResult:
    """Return a clean A-share universe frame with defensive eligibility filters."""

    frame = stock_basic.copy()
    original_count = int(len(frame))
    if "ts_code" not in frame:
        frame["ts_code"] = pd.Series(dtype=str)
    if "name" not in frame:
        frame["name"] = ""

    frame["ts_code"] = frame["ts_code"].astype(str).str.strip().str.upper()
    frame["name"] = frame["name"].astype(str).str.strip()
    frame = frame[frame["ts_code"].str.match(r"^\d{6}\.(SH|SZ|BJ)$", na=False)]
    valid_code_count = int(len(frame))

    risky_name = frame["name"].str.contains(r"(?:退|退市|摘牌|终止|^\*?ST|^SST|^NST)", case=False, na=False)
    frame = frame[~risky_name]
    after_name_filter = int(len(frame))

    for column in ("list_status", "status"):
        if column in frame:
            status = frame[column].astype(str).str.upper()
            frame = frame[status.isin({"L", "LISTED", "上市", "1", "TRUE"}) | status.eq("")]

    for column in ("is_suspended", "suspended", "suspend"):
        if column in frame:
            suspended = frame[column].astype(str).str.lower().isin({"1", "true", "yes", "y", "suspended"})
            frame = frame[~suspended]

    if "list_date" in frame:
        today = as_of or date.today()
        list_dates = pd.to_datetime(frame["list_date"], format="%Y%m%d", errors="coerce")
        age_days = (pd.Timestamp(today) - list_dates).dt.days
        frame = frame[(list_dates.isna()) | (age_days >= 180)]

    result = frame.drop_duplicates("ts_code").sort_values("ts_code").reset_index(drop=True)
    return UniverseFilterResult(
        frame=result,
        stats={
            "raw": original_count,
            "valid_code": valid_code_count,
            "after_name_filter": after_name_filter,
            "eligible": int(len(result)),
        },
    )
