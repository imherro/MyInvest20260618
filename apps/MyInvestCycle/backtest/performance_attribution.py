from __future__ import annotations

from typing import Iterable

import pandas as pd

from core.alpha_validation_engine import compound_return, hit_rate


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def build_state_attribution(
    frame: pd.DataFrame,
    *,
    state_columns: Iterable[str],
    strategy_column: str = "v2_return",
    benchmark_column: str = "benchmark_510500_return",
) -> dict[str, dict[str, dict[str, object]]]:
    result: dict[str, dict[str, dict[str, object]]] = {}
    for state_column in state_columns:
        if state_column not in frame:
            continue
        state_result: dict[str, dict[str, object]] = {}
        for state, group in frame.groupby(state_column, dropna=False):
            strategy_total = compound_return(group[strategy_column].fillna(0.0))
            benchmark_total = compound_return(group[benchmark_column].fillna(0.0))
            state_result[str(state or "unknown")] = {
                "sessions": int(len(group)),
                "strategy_return": _round(strategy_total),
                "benchmark_return": _round(benchmark_total),
                "alpha": _round(strategy_total - benchmark_total),
                "hit_rate": _round(hit_rate(group[strategy_column].fillna(0.0), group[benchmark_column].fillna(0.0))),
                "average_exposure": _round(float(group.get("target_exposure", pd.Series(dtype=float)).fillna(0.0).mean())),
            }
        result[state_column] = state_result
    return result
