from __future__ import annotations

from typing import Mapping


MODEL_NAME = "trend_following"


def score_trend_following(features: Mapping[str, object]) -> dict[str, object]:
    components = {
        "momentum": float(features["momentum"]),
        "trend_quality": float(features["trend_quality"]),
        "relative_strength": float(features["relative_strength"]),
        "risk_adjusted": float(features["risk_adjusted"]),
    }
    score = (
        0.40 * components["momentum"]
        + 0.30 * components["trend_quality"]
        + 0.20 * components["relative_strength"]
        + 0.10 * components["risk_adjusted"]
    )
    return {
        "model": MODEL_NAME,
        "model_score": round(max(0.0, min(100.0, score)), 4),
        "components": {key: round(value, 4) for key, value in components.items()},
        "explanation": [
            "Trend model is intended for broad bull regimes.",
            "It rewards momentum, moving-average trend quality and relative strength.",
            "It does not create allocation or trade instructions.",
        ],
    }
