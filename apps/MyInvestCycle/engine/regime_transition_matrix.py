from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import pandas as pd

from core.data_loader import normalize_trade_date
from engine.market_engine import analyze_index_regime


REGIMES = ("bull", "bear", "range", "transition")


MarketDailyLoader = Callable[[str], pd.DataFrame]
MarketHistoryLoader = Callable[[str, pd.DataFrame], pd.DataFrame | None]


@dataclass(frozen=True)
class RegimeSequenceResult:
    items: list[dict[str, object]]
    skipped: list[dict[str, str]]

    @property
    def regimes(self) -> list[str]:
        return [str(item["regime"]) for item in self.items]


def empty_transition_counts(regimes: Sequence[str] = REGIMES) -> dict[str, dict[str, int]]:
    return {source: {target: 0 for target in regimes} for source in regimes}


def count_transitions(
    regime_sequence: Iterable[str],
    *,
    regimes: Sequence[str] = REGIMES,
) -> dict[str, dict[str, int]]:
    counts = empty_transition_counts(regimes)
    allowed = set(regimes)
    previous: str | None = None
    for regime in regime_sequence:
        if regime not in allowed:
            raise ValueError(f"Unknown regime: {regime!r}")
        if previous is not None:
            counts[previous][regime] += 1
        previous = regime
    return counts


def normalize_transition_counts(
    counts: Mapping[str, Mapping[str, int]],
    *,
    regimes: Sequence[str] = REGIMES,
    precision: int = 6,
) -> dict[str, dict[str, float]]:
    matrix: dict[str, dict[str, float]] = {}
    for source in regimes:
        row_counts = counts.get(source, {})
        total = sum(int(row_counts.get(target, 0)) for target in regimes)
        if total == 0:
            matrix[source] = {target: 0.0 for target in regimes}
            continue

        row = {
            target: round(int(row_counts.get(target, 0)) / total, precision)
            for target in regimes
        }
        adjustment = round(1.0 - sum(row.values()), precision)
        if adjustment:
            largest_target = max(regimes, key=lambda target: row[target])
            row[largest_target] = round(row[largest_target] + adjustment, precision)
        matrix[source] = row
    return matrix


def build_transition_matrix(
    regime_sequence: Iterable[str],
    *,
    regimes: Sequence[str] = REGIMES,
    precision: int = 6,
) -> dict[str, dict[str, float]]:
    counts = count_transitions(regime_sequence, regimes=regimes)
    return normalize_transition_counts(counts, regimes=regimes, precision=precision)


def transition_row_sums(matrix: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
    return {source: round(sum(float(value) for value in row.values()), 6) for source, row in matrix.items()}


def validate_transition_matrix(
    matrix: Mapping[str, Mapping[str, float]],
    *,
    counts: Mapping[str, Mapping[str, int]] | None = None,
    regimes: Sequence[str] = REGIMES,
) -> None:
    for source in regimes:
        if source not in matrix:
            raise ValueError(f"Missing transition row: {source}")
        row = matrix[source]
        for target in regimes:
            if target not in row:
                raise ValueError(f"Missing transition cell: {source}->{target}")
            value = float(row[target])
            if value < 0.0 or value > 1.0:
                raise ValueError(f"Transition probability out of range: {source}->{target}={value}")

        row_has_samples = True
        if counts is not None:
            row_has_samples = sum(int(counts.get(source, {}).get(target, 0)) for target in regimes) > 0

        row_sum = round(sum(float(row[target]) for target in regimes), 6)
        expected = 1.0 if row_has_samples else 0.0
        if abs(row_sum - expected) > 1e-6:
            raise ValueError(f"Transition row {source!r} sums to {row_sum}, expected {expected}")


def build_daily_regime_sequence(
    index_df: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    market_daily_loader: MarketDailyLoader,
    hsgt_df: pd.DataFrame | None = None,
    market_history_loader: MarketHistoryLoader | None = None,
    skip_errors: bool = False,
) -> RegimeSequenceResult:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date.")

    if index_df.empty:
        raise ValueError("index_df is empty")
    if "trade_date" not in index_df.columns:
        raise KeyError("index_df must contain trade_date")

    index_history = index_df.copy()
    index_history["trade_date"] = index_history["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    index_history = index_history.sort_values("trade_date").reset_index(drop=True)
    target_dates = index_history[
        (index_history["trade_date"] >= start) & (index_history["trade_date"] <= end)
    ]["trade_date"].astype(str).tolist()

    hsgt_history = None
    if hsgt_df is not None and not hsgt_df.empty:
        hsgt_history = hsgt_df.copy()
        hsgt_history["trade_date"] = hsgt_history["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
        hsgt_history = hsgt_history.sort_values("trade_date").reset_index(drop=True)

    items: list[dict[str, object]] = []
    skipped: list[dict[str, str]] = []
    for trade_date in target_dates:
        try:
            index_slice = index_history[index_history["trade_date"] <= trade_date].copy()
            market_daily = market_daily_loader(trade_date)
            market_history = None
            if market_history_loader is not None:
                market_history = market_history_loader(trade_date, market_daily)
            hsgt_slice = None
            if hsgt_history is not None:
                hsgt_slice = hsgt_history[hsgt_history["trade_date"] <= trade_date].tail(30).copy()

            result = analyze_index_regime(
                index_slice,
                market_daily_df=market_daily,
                market_history_df=market_history,
                hsgt_df=hsgt_slice,
            )
            items.append(
                {
                    "trade_date": trade_date,
                    "regime": str(result["regime"]),
                    "confidence": float(result["confidence"]),
                    "trend_score": float(result["trend_score"]),
                    "breadth_score": float(result["breadth_score"]),
                    "liquidity_score": float(result["liquidity_score"]),
                    "volatility_score": float(result["volatility_score"]),
                    "regime_score": float(result["regime_score"]),
                }
            )
        except Exception as exc:
            if not skip_errors:
                raise
            skipped.append({"trade_date": trade_date, "reason": str(exc)})

    return RegimeSequenceResult(items=items, skipped=skipped)


def save_transition_matrix(matrix: Mapping[str, Mapping[str, float]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(matrix, ensure_ascii=False, indent=2)
    path.write_text(data + "\n", encoding="utf-8")
    return path
