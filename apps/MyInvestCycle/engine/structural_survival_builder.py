from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from engine.regime_duration_builder import save_survival_dataset, survival_dataset_summary
from engine.regime_hazard_labeler import build_hazard_feature_snapshot, ordered_regime_items
from engine.regime_hazard_labeler_v2 import detect_structural_break_indices, smooth_regime_sequence


def build_macro_regime_sequence(
    raw_regimes: Sequence[str],
    *,
    smooth_radius: int = 3,
    persistence_days: int = 3,
    min_break_gap: int = 20,
) -> dict[str, object]:
    smoothed = smooth_regime_sequence(raw_regimes, radius=smooth_radius)
    break_indices = detect_structural_break_indices(
        smoothed,
        persistence_days=persistence_days,
        min_break_gap=min_break_gap,
    )
    accepted_breaks = set(break_indices)

    macro_regimes: list[str] = []
    current = smoothed[0]
    macro_change_indices: list[int] = []
    for index, regime in enumerate(smoothed):
        if index in accepted_breaks and regime != current:
            current = regime
            macro_change_indices.append(index)
        macro_regimes.append(current)

    return {
        "smoothed_regimes": smoothed,
        "break_indices": break_indices,
        "macro_change_indices": macro_change_indices,
        "macro_regimes": macro_regimes,
    }


def build_structural_survival_dataset(
    regime_items: Sequence[Mapping[str, object]],
    *,
    smooth_radius: int = 3,
    persistence_days: int = 3,
    min_break_gap: int = 20,
) -> list[dict[str, object]]:
    ordered = ordered_regime_items(regime_items)
    if len(ordered) < 2:
        raise ValueError("At least two regime observations are required.")

    raw_regimes = [str(item["regime"]) for item in ordered]
    macro = build_macro_regime_sequence(
        raw_regimes,
        smooth_radius=smooth_radius,
        persistence_days=persistence_days,
        min_break_gap=min_break_gap,
    )
    macro_regimes = list(macro["macro_regimes"])

    dataset: list[dict[str, object]] = []
    duration = 0
    previous_regime: str | None = None
    for index, current in enumerate(ordered[:-1]):
        structural_regime = str(macro_regimes[index])
        if structural_regime == previous_regime:
            duration += 1
        else:
            duration = 1

        features = build_hazard_feature_snapshot(ordered, index, duration)
        features["regime_age"] = int(duration)
        features["structural_regime_age"] = int(duration)

        next_structural_regime = str(macro_regimes[index + 1])
        dataset.append(
            {
                "date": str(current["trade_date"]),
                "raw_regime": raw_regimes[index],
                "structural_regime": structural_regime,
                "duration": int(duration),
                "event": 1 if next_structural_regime != structural_regime else 0,
                "features": features,
            }
        )
        previous_regime = structural_regime

    return dataset


def validate_structural_survival_dataset(
    dataset: Sequence[Mapping[str, object]],
    *,
    max_event_rate: float = 0.15,
    min_bull_duration: int = 10,
) -> None:
    if not dataset:
        raise ValueError("structural survival dataset is empty")
    summary = survival_dataset_summary(
        [
            {
                "date": item["date"],
                "regime": item["structural_regime"],
                "duration": item["duration"],
                "event": item["event"],
                "features": item["features"],
            }
            for item in dataset
        ]
    )
    event_rate = float(summary["event_rate"])
    if event_rate >= max_event_rate:
        raise ValueError(f"event_rate {event_rate:.6f} exceeds threshold {max_event_rate:.6f}")

    bull_summary = summary["regime_duration_summary"].get("bull")
    if bull_summary is not None and int(bull_summary["max_duration"]) <= min_bull_duration:
        raise ValueError(
            f"bull max_duration {bull_summary['max_duration']} must be greater than {min_bull_duration}"
        )


def structural_survival_summary(dataset: Sequence[Mapping[str, object]]) -> dict[str, object]:
    normalized = [
        {
            "date": item["date"],
            "regime": item["structural_regime"],
            "duration": item["duration"],
            "event": item["event"],
            "features": item["features"],
        }
        for item in dataset
    ]
    return survival_dataset_summary(normalized)


def save_structural_survival_dataset(dataset: Sequence[Mapping[str, object]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(dataset), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
