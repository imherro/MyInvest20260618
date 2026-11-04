"""Standard TASK 1 dataframe schema."""

from __future__ import annotations

import pandas as pd


STANDARD_COLUMNS = [
    "ts_code",
    "date",
    "open",
    "high",
    "low",
    "close",
    "revenue",
    "net_profit",
    "roe",
    "pe",
    "pb",
    "market_cap",
]

METADATA_COLUMNS = [
    "name",
    "industry",
    "area",
    "list_date",
    "source",
    "ann_date",
    "report_period",
    "operating_cashflow",
    "debt_ratio",
]

NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "revenue",
    "net_profit",
    "roe",
    "pe",
    "pb",
    "market_cap",
    "operating_cashflow",
    "debt_ratio",
]


def empty_standard_frame() -> pd.DataFrame:
    """Return an empty dataframe with all known output columns."""

    return pd.DataFrame(columns=STANDARD_COLUMNS + METADATA_COLUMNS)


def ensure_standard_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure required columns exist, numeric columns are numeric, and order is stable."""

    result = df.copy()
    for column in STANDARD_COLUMNS + METADATA_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    for column in NUMERIC_COLUMNS:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")

    if "date" in result.columns:
        result["date"] = result["date"].astype(str)

    ordered = STANDARD_COLUMNS + METADATA_COLUMNS
    extras = [column for column in result.columns if column not in ordered]
    return result[ordered + extras]
