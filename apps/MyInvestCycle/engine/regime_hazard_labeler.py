from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from core.data_loader import normalize_trade_date


BASE_FEATURE_KEYS = ("trend", "breadth", "liquidity", "volatility")


def _round(value: float) -> float:
    return round(float(value), 6)


def _score(item: Mapping[str, object], key: str) -> float:
    direct_key = f"{key}_score"
    if direct_key in item:
        return float(item[direct_key])

    sub_scores = item.get("sub_scores")
    if isinstance(sub_scores, Mapping) and key in sub_scores:
        return float(sub_scores[key])

    raise KeyError(f"Missing {direct_key} for {item.get('trade_date', '<unknown date>')}")


def _ordered_items(regime_items: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    ordered: list[dict[str, object]] = []
    for item in regime_items:
        if "trade_date" not in item:
            raise KeyError("Each regime item must contain trade_date")
        if "regime" not in item:
            raise KeyError("Each regime item must contain regime")

        normalized = dict(item)
        normalized["trade_date"] = normalize_trade_date(normalized["trade_date"])
        normalized["regime"] = str(normalized["regime"])
        ordered.append(normalized)

    return sorted(ordered, key=lambda item: str(item["trade_date"]))


def ordered_regime_items(regime_items: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return _ordered_items(regime_items)


def _feature_snapshot(
    ordered: Sequence[Mapping[str, object]],
    index: int,
    persistence: int,
) -> dict[str, float | int]:
    item = ordered[index]
    trend = _score(item, "trend")
    breadth = _score(item, "breadth")
    liquidity = _score(item, "liquidity")
    volatility = _score(item, "volatility")

    momentum_decay = 0.0
    if index >= 5:
        momentum_decay = trend - _score(ordered[index - 5], "trend")

    liquidity_acceleration = 0.0
    if index >= 3:
        liquidity_acceleration = liquidity - _score(ordered[index - 3], "liquidity")

    volatility_shock = 1.0
    if index >= 10:
        previous_volatility = _score(ordered[index - 10], "volatility")
        if previous_volatility:
            volatility_shock = volatility / previous_volatility

    features: dict[str, float | int] = {
        "trend": _round(trend),
        "breadth": _round(breadth),
        "liquidity": _round(liquidity),
        "volatility": _round(volatility),
        "pressure": _round(abs(trend - breadth)),
        "momentum_decay": _round(momentum_decay),
        "liquidity_acceleration": _round(liquidity_acceleration),
        "volatility_shock": _round(volatility_shock),
        "regime_persistence": int(persistence),
    }

    if "regime_score" in item:
        features["regime_score"] = _round(float(item["regime_score"]))
    if "confidence" in item:
        features["confidence"] = _round(float(item["confidence"]))

    return features


def build_hazard_feature_snapshot(
    ordered: Sequence[Mapping[str, object]],
    index: int,
    persistence: int,
) -> dict[str, float | int]:
    return _feature_snapshot(ordered, index, persistence)


def build_hazard_dataset(regime_items: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Build X_t -> y_t samples without using future data in features."""

    ordered = _ordered_items(regime_items)
    if len(ordered) < 2:
        raise ValueError("At least two regime observations are required.")

    dataset: list[dict[str, object]] = []
    persistence = 0
    previous_regime: str | None = None

    for index, current in enumerate(ordered[:-1]):
        current_regime = str(current["regime"])
        if current_regime == previous_regime:
            persistence += 1
        else:
            persistence = 1

        next_regime = str(ordered[index + 1]["regime"])
        dataset.append(
            {
                "date": str(current["trade_date"]),
                "regime": current_regime,
                "features": _feature_snapshot(ordered, index, persistence),
                "label": 1 if current_regime != next_regime else 0,
            }
        )
        previous_regime = current_regime

    return dataset


def hazard_label_distribution(dataset: Sequence[Mapping[str, object]]) -> dict[str, object]:
    labels = [int(item["label"]) for item in dataset]
    counts = Counter(labels)
    total = len(labels)
    transition_events = int(counts.get(1, 0))
    continuation_events = int(counts.get(0, 0))
    return {
        "observations": int(total),
        "transition_events": transition_events,
        "continuation_events": continuation_events,
        "transition_rate": _round(transition_events / total) if total else 0.0,
        "continuation_rate": _round(continuation_events / total) if total else 0.0,
    }


def validate_hazard_dataset(dataset: Sequence[Mapping[str, object]]) -> None:
    if not dataset:
        raise ValueError("hazard dataset is empty")

    dates = [normalize_trade_date(item["date"]) for item in dataset]
    if dates != sorted(dates):
        raise ValueError("hazard dataset must be sorted by date")

    for item in dataset:
        label = int(item["label"])
        if label not in {0, 1}:
            raise ValueError(f"Invalid hazard label: {label}")

        features = item.get("features")
        if not isinstance(features, Mapping):
            raise ValueError(f"Missing features for {item.get('date')}")
        for key in BASE_FEATURE_KEYS:
            if key not in features:
                raise ValueError(f"Missing feature {key!r} for {item.get('date')}")


def save_hazard_dataset(dataset: Sequence[Mapping[str, object]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(dataset), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
