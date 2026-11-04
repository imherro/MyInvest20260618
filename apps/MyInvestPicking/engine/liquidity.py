from __future__ import annotations

import pandas as pd

MIN_LATEST_AMOUNT = 30_000.0
MIN_TURNOVER_RATE = 0.5


def filter_liquidity(
    factors: pd.DataFrame,
    min_latest_amount: float = MIN_LATEST_AMOUNT,
    min_turnover_rate: float = MIN_TURNOVER_RATE,
) -> pd.DataFrame:
    if factors.empty:
        return factors.copy()

    filtered = factors.copy()
    mask = pd.Series(True, index=filtered.index)

    if "latest_amount" in filtered.columns:
        latest_amount = pd.to_numeric(filtered["latest_amount"], errors="coerce")
        mask &= latest_amount >= min_latest_amount

    if "turnover_rate" in filtered.columns:
        turnover_rate = pd.to_numeric(filtered["turnover_rate"], errors="coerce")
        mask &= turnover_rate >= min_turnover_rate

    return filtered[mask].reset_index(drop=True)
