from __future__ import annotations

from typing import Any

from strategy.core_strategy import build_stock_picks


def run_live_pipeline(trade_date: str | None = None, top_n: int = 20) -> dict[str, Any]:
    return build_stock_picks(trade_date=trade_date, top_n=top_n)
