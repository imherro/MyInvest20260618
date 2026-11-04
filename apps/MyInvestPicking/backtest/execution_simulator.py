from __future__ import annotations


DEFAULT_TRANSACTION_COST = 0.001
DEFAULT_SLIPPAGE = 0.0015


def execution_cost(
    turnover: float,
    transaction_cost: float = DEFAULT_TRANSACTION_COST,
    slippage: float = DEFAULT_SLIPPAGE,
) -> float:
    return max(turnover, 0.0) * (transaction_cost + slippage)


def fill_ratio_for_day(is_tradeable: bool = True) -> float:
    return 1.0 if is_tradeable else 0.0
