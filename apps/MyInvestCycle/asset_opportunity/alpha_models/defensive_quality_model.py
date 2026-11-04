from __future__ import annotations

from typing import Mapping


MODEL_NAME = "defensive_quality"


def score_defensive_quality(features: Mapping[str, object]) -> dict[str, object]:
    components = {
        "low_volatility": float(features["low_volatility"]),
        "drawdown_control": float(features["drawdown_control"]),
        "relative_resilience": float(features["relative_strength"]),
        "extension_safety": max(0.0, 100.0 - float(features["extension_penalty"]) / 30.0 * 100.0),
    }
    score = (
        0.35 * components["low_volatility"]
        + 0.30 * components["drawdown_control"]
        + 0.20 * components["relative_resilience"]
        + 0.15 * components["extension_safety"]
    )
    return {
        "model": MODEL_NAME,
        "model_score": round(max(0.0, min(100.0, score)), 4),
        "components": {key: round(value, 4) for key, value in components.items()},
        "explanation": [
            "Defensive quality model is intended for bear or high-crowding regimes.",
            "It rewards lower volatility, shallower drawdown and relative resilience.",
            "It does not output defensive allocation weights.",
        ],
    }
