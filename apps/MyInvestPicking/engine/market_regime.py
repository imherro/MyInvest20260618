from __future__ import annotations

from typing import Literal


MarketRegimeState = Literal["trend", "range", "crash", "high_vol"]


def detect_market_regime(features: dict[str, float | int]) -> dict[str, float | str]:
    return_5d = float(features.get("return_5d") or 0)
    return_20d = float(features.get("return_20d") or 0)
    return_60d = float(features.get("return_60d") or 0)
    volatility = float(features.get("volatility_20d") or 0)
    volume_trend = float(features.get("volume_trend_20d") or 0)

    if return_20d <= -0.05 or (return_5d <= -0.03 and volatility >= 0.025):
        state: MarketRegimeState = "crash"
        confidence = min(1.0, 0.55 + abs(return_20d) * 4 + volatility * 4)
    elif volatility >= 0.03:
        state = "high_vol"
        confidence = min(1.0, 0.50 + volatility * 8)
    elif return_20d >= 0.03 and return_60d >= 0 and volume_trend >= -0.20:
        state = "trend"
        confidence = min(1.0, 0.55 + return_20d * 4 + max(volume_trend, 0) * 0.2)
    else:
        state = "range"
        confidence = min(1.0, 0.55 + max(0.0, 0.03 - abs(return_20d)) * 5)

    return {
        "state": state,
        "confidence": round(confidence, 4),
        "return_5d": round(return_5d, 6),
        "return_20d": round(return_20d, 6),
        "return_60d": round(return_60d, 6),
        "volatility_20d": round(volatility, 6),
        "volume_trend_20d": round(volume_trend, 6),
    }
