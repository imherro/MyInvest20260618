from __future__ import annotations

from typing import Mapping


MODEL_NAME = "mean_reversion"


def score_mean_reversion(features: Mapping[str, object]) -> dict[str, object]:
    price_percentile = float(features["price_percentile_252"])
    deviation_ma120 = float(features["deviation_ma120"])
    pullback_depth = max(0.0, min(100.0, (0.55 - price_percentile) / 0.55 * 100.0))
    ma_discount = max(0.0, min(100.0, (-deviation_ma120) / 0.18 * 100.0))
    trend_floor = float(features["trend_quality"])
    volatility_control = float(features["low_volatility"])
    components = {
        "pullback_depth": pullback_depth,
        "ma_discount": ma_discount,
        "trend_floor": trend_floor,
        "volatility_control": volatility_control,
    }
    score = (
        0.35 * components["pullback_depth"]
        + 0.25 * components["ma_discount"]
        + 0.20 * components["trend_floor"]
        + 0.20 * components["volatility_control"]
    )
    return {
        "model": MODEL_NAME,
        "model_score": round(max(0.0, min(100.0, score)), 4),
        "components": {key: round(value, 4) for key, value in components.items()},
        "explanation": [
            "Mean reversion model is intended for range regimes.",
            "It rewards pullbacks toward lower price positions while keeping trend and volatility filters visible.",
            "It is not a buy signal or sizing instruction.",
        ],
    }
