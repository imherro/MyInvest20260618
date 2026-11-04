from __future__ import annotations

from typing import Mapping


MODEL_NAME = "rotation_alpha"


def score_rotation_alpha(features: Mapping[str, object]) -> dict[str, object]:
    extension_safety = max(0.0, 100.0 - float(features["extension_penalty"]) / 30.0 * 100.0)
    rotation_stability = max(0.0, 100.0 - abs(float(features["return20_score"]) - float(features["return60_score"])))
    components = {
        "relative_strength": float(features["relative_strength"]),
        "persistence": float(features["persistence"]),
        "rotation_stability": rotation_stability,
        "extension_safety": extension_safety,
    }
    score = (
        0.30 * components["relative_strength"]
        + 0.30 * components["persistence"]
        + 0.25 * components["rotation_stability"]
        + 0.15 * components["extension_safety"]
    )
    return {
        "model": MODEL_NAME,
        "model_score": round(max(0.0, min(100.0, score)), 4),
        "components": {key: round(value, 4) for key, value in components.items()},
        "explanation": [
            "Rotation model is intended for structural bull regimes.",
            "It reduces pure chase behavior by including persistence, stability and extension safety.",
            "It is a research score only, not a portfolio weight.",
        ],
    }
