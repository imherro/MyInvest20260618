from __future__ import annotations

import math
from collections import Counter
from typing import Mapping, Sequence

from engine.regime_hazard_labeler import (
    build_hazard_feature_snapshot,
    hazard_label_distribution,
    ordered_regime_items,
    save_hazard_dataset,
    validate_hazard_dataset,
)


LABEL_TYPE = "structural_break"


def _mode_with_current_preference(regimes: Sequence[str], index: int, radius: int) -> str:
    if radius < 0:
        raise ValueError("smooth radius must be non-negative")

    start = max(0, index - radius)
    end = min(len(regimes), index + radius + 1)
    window = list(regimes[start:end])
    counts = Counter(window)
    best_count = max(counts.values())
    candidates = [regime for regime, count in counts.items() if count == best_count]
    current = regimes[index]
    if current in candidates:
        return current
    return sorted(candidates)[0]


def smooth_regime_sequence(regimes: Sequence[str], *, radius: int = 3) -> list[str]:
    if not regimes:
        return []
    return [_mode_with_current_preference(regimes, index, radius) for index in range(len(regimes))]


def detect_structural_break_indices(
    smoothed_regimes: Sequence[str],
    *,
    persistence_days: int = 3,
    min_break_gap: int = 20,
) -> list[int]:
    if persistence_days <= 0:
        raise ValueError("persistence_days must be positive")
    if min_break_gap < 0:
        raise ValueError("min_break_gap must be non-negative")

    break_indices: list[int] = []
    last_break = -10**9
    for index in range(1, len(smoothed_regimes)):
        previous_regime = smoothed_regimes[index - 1]
        current_regime = smoothed_regimes[index]
        if current_regime == previous_regime:
            continue
        if index + persistence_days > len(smoothed_regimes):
            continue
        if any(smoothed_regimes[future] != current_regime for future in range(index, index + persistence_days)):
            continue
        if index - last_break < min_break_gap:
            continue
        break_indices.append(index)
        last_break = index
    return break_indices


def _structural_persistence(smoothed_regimes: Sequence[str]) -> list[int]:
    persistence: list[int] = []
    previous: str | None = None
    count = 0
    for regime in smoothed_regimes:
        if regime == previous:
            count += 1
        else:
            count = 1
        persistence.append(count)
        previous = regime
    return persistence


def build_structural_hazard_dataset(
    regime_items: Sequence[Mapping[str, object]],
    *,
    smooth_radius: int = 3,
    persistence_days: int = 3,
    forward_window: int = 5,
    min_break_gap: int = 20,
) -> list[dict[str, object]]:
    """Build labels for macro structural breaks within a future trading-day window."""

    if forward_window <= 0:
        raise ValueError("forward_window must be positive")

    ordered = ordered_regime_items(regime_items)
    if len(ordered) <= forward_window:
        raise ValueError("Not enough regime observations for the requested forward_window.")

    raw_regimes = [str(item["regime"]) for item in ordered]
    smoothed_regimes = smooth_regime_sequence(raw_regimes, radius=smooth_radius)
    break_indices = set(
        detect_structural_break_indices(
            smoothed_regimes,
            persistence_days=persistence_days,
            min_break_gap=min_break_gap,
        )
    )
    persistence = _structural_persistence(smoothed_regimes)

    dataset: list[dict[str, object]] = []
    max_index = len(ordered) - forward_window
    for index in range(max_index):
        label = 1 if any(index < break_index <= index + forward_window for break_index in break_indices) else 0
        dataset.append(
            {
                "date": str(ordered[index]["trade_date"]),
                "regime": raw_regimes[index],
                "structural_regime": smoothed_regimes[index],
                "features": build_hazard_feature_snapshot(ordered, index, persistence[index]),
                "label": label,
                "label_type": LABEL_TYPE,
            }
        )

    return dataset


def structural_hazard_diagnostics(
    dataset: Sequence[Mapping[str, object]],
    *,
    smoothed_regimes: Sequence[str],
    break_indices: Sequence[int],
    max_hazard_rate: float = 0.15,
) -> dict[str, object]:
    distribution = hazard_label_distribution(dataset)
    hazard_rate = float(distribution["transition_rate"])
    entropy = 0.0
    for rate in (hazard_rate, 1.0 - hazard_rate):
        if rate > 0.0:
            entropy -= rate * math.log2(rate)

    return {
        "label_distribution": distribution,
        "label_entropy": round(entropy, 6),
        "hazard_rate_threshold": float(max_hazard_rate),
        "hazard_rate_status": "pass" if hazard_rate < max_hazard_rate else "fail",
        "structural_break_events": int(len(break_indices)),
        "smoothed_regime_counts": dict(Counter(smoothed_regimes)),
    }


def validate_structural_hazard_dataset(
    dataset: Sequence[Mapping[str, object]],
    *,
    max_hazard_rate: float = 0.15,
) -> None:
    validate_hazard_dataset(dataset)
    for item in dataset:
        if item.get("label_type") != LABEL_TYPE:
            raise ValueError(f"Invalid structural label_type for {item.get('date')}")
        if "structural_regime" not in item:
            raise ValueError(f"Missing structural_regime for {item.get('date')}")

    hazard_rate = float(hazard_label_distribution(dataset)["transition_rate"])
    if hazard_rate >= max_hazard_rate:
        raise ValueError(f"Structural hazard rate {hazard_rate:.6f} exceeds threshold {max_hazard_rate:.6f}")


__all__ = [
    "LABEL_TYPE",
    "build_structural_hazard_dataset",
    "detect_structural_break_indices",
    "save_hazard_dataset",
    "smooth_regime_sequence",
    "structural_hazard_diagnostics",
    "validate_structural_hazard_dataset",
]
