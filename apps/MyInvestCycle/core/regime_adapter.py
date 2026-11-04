from __future__ import annotations

from typing import Mapping


RISK_SIGNAL_KEYS = (
    "as_of",
    "regime",
    "confidence",
    "trend",
    "breadth",
    "liquidity",
    "volatility",
    "regime_score",
)


def _score(payload: Mapping[str, object], score_name: str) -> float:
    direct_key = f"{score_name}_score"
    if direct_key in payload:
        return round(float(payload[direct_key]), 6)

    sub_scores = payload.get("sub_scores")
    if isinstance(sub_scores, Mapping) and score_name in sub_scores:
        return round(float(sub_scores[score_name]), 6)

    raise KeyError(f"Missing regime score field: {direct_key}")


def adapt_regime_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Normalize a MyInvestCycle regime payload into a risk-engine input signal."""

    signal = {
        "as_of": payload.get("as_of"),
        "regime": str(payload["regime"]),
        "confidence": round(float(payload.get("confidence", 0.0)), 6),
        "trend": _score(payload, "trend"),
        "breadth": _score(payload, "breadth"),
        "liquidity": _score(payload, "liquidity"),
        "volatility": _score(payload, "volatility"),
        "regime_score": round(float(payload.get("regime_score", 0.0)), 6),
    }
    validate_risk_signal(signal)
    return signal


def validate_risk_signal(signal: Mapping[str, object]) -> None:
    missing = [key for key in RISK_SIGNAL_KEYS if key not in signal]
    if missing:
        raise ValueError(f"Missing risk signal keys: {missing}")

    if str(signal["regime"]) not in {"bull", "bear", "range", "transition"}:
        raise ValueError(f"Unknown regime: {signal['regime']!r}")

    for key in ("confidence", "trend", "breadth", "liquidity", "volatility", "regime_score"):
        value = float(signal[key])
        if value < 0.0 or value > 1.0:
            raise ValueError(f"{key} must be between 0 and 1, got {value}")
