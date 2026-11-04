from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence

from core.data_loader import normalize_trade_date
from engine.regime_hazard_labeler import build_hazard_feature_snapshot, ordered_regime_items


def _score(item: Mapping[str, object], key: str) -> float:
    direct_key = f"{key}_score"
    if direct_key in item:
        return float(item[direct_key])
    features = item.get("features")
    if isinstance(features, Mapping) and key in features:
        return float(features[key])
    raise KeyError(f"Missing {direct_key} for {item.get('trade_date', '<unknown date>')}")


def _window_delta(
    ordered: Sequence[Mapping[str, object]],
    index: int,
    key: str,
    lookback: int,
) -> float:
    if index < lookback:
        return 0.0
    return round(_score(ordered[index], key) - _score(ordered[index - lookback], key), 6)


def build_survival_dataset(regime_items: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Build regime duration/event samples using only t and earlier feature data."""

    ordered = ordered_regime_items(regime_items)
    if len(ordered) < 2:
        raise ValueError("At least two regime observations are required.")

    dataset: list[dict[str, object]] = []
    duration = 0
    previous_regime: str | None = None
    for index, current in enumerate(ordered[:-1]):
        regime = str(current["regime"])
        if regime == previous_regime:
            duration += 1
        else:
            duration = 1

        features = build_hazard_feature_snapshot(ordered, index, duration)
        features["regime_age"] = int(duration)
        features["trend_decay_20"] = _window_delta(ordered, index, "trend", 20)
        features["liquidity_shift_20"] = _window_delta(ordered, index, "liquidity", 20)
        features["volatility_acceleration_20"] = _window_delta(ordered, index, "volatility", 20)

        next_regime = str(ordered[index + 1]["regime"])
        dataset.append(
            {
                "date": str(current["trade_date"]),
                "regime": regime,
                "duration": int(duration),
                "event": 1 if next_regime != regime else 0,
                "features": features,
            }
        )
        previous_regime = regime

    return dataset


def validate_survival_dataset(dataset: Sequence[Mapping[str, object]]) -> None:
    if not dataset:
        raise ValueError("survival dataset is empty")

    dates = [normalize_trade_date(row["date"]) for row in dataset]
    if dates != sorted(dates):
        raise ValueError("survival dataset must be sorted by date")

    previous_regime: str | None = None
    previous_duration = 0
    for row in dataset:
        regime = str(row["regime"])
        duration = int(row["duration"])
        event = int(row["event"])
        if event not in {0, 1}:
            raise ValueError(f"Invalid event value for {row.get('date')}: {event}")
        if regime == previous_regime:
            expected_duration = previous_duration + 1
        else:
            expected_duration = 1
        if duration != expected_duration:
            raise ValueError(
                f"Invalid duration for {row.get('date')}: {duration}, expected {expected_duration}"
            )
        features = row.get("features")
        if not isinstance(features, Mapping):
            raise ValueError(f"Missing features for {row.get('date')}")
        if int(features.get("regime_age", -1)) != duration:
            raise ValueError(f"regime_age mismatch for {row.get('date')}")

        previous_regime = regime
        previous_duration = duration


def survival_dataset_summary(dataset: Sequence[Mapping[str, object]]) -> dict[str, object]:
    total = len(dataset)
    events = sum(int(row["event"]) for row in dataset)
    durations_by_regime: dict[str, list[int]] = defaultdict(list)
    for row in dataset:
        durations_by_regime[str(row["regime"])].append(int(row["duration"]))

    regime_summary: dict[str, dict[str, float | int]] = {}
    for regime, durations in sorted(durations_by_regime.items()):
        regime_summary[regime] = {
            "observations": int(len(durations)),
            "max_duration": int(max(durations)),
            "avg_duration": round(sum(durations) / len(durations), 6),
        }

    return {
        "observations": int(total),
        "events": int(events),
        "censored_or_continuing": int(total - events),
        "event_rate": round(events / total, 6) if total else 0.0,
        "regime_duration_summary": regime_summary,
    }


def save_survival_dataset(dataset: Sequence[Mapping[str, object]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(dataset), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
