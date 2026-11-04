from __future__ import annotations

from dataclasses import dataclass


MARKET_PHASES = (
    "EARLY_CYCLE",
    "EXPANSION",
    "ROTATION",
    "LATE_CYCLE",
    "CONTRACTION",
    "UNKNOWN",
)


@dataclass(frozen=True)
class MarketPhaseResult:
    phase: str
    evidence: tuple[str, ...]
    metrics: dict[str, object]
    interpretation: str


def normalize_market_phase(value: object) -> str:
    text = str(value or "UNKNOWN").strip().upper()
    return text if text in MARKET_PHASES else "UNKNOWN"


def phase_interpretation(phase: str) -> str:
    labels = {
        "EARLY_CYCLE": "Recovery is visible but still needs confirmation from trend and breadth.",
        "EXPANSION": "Trend, breadth, and liquidity are aligned enough to describe an expansion phase.",
        "ROTATION": "Theme persistence is visible while breadth is not broad enough; market is rotating rather than broadening.",
        "LATE_CYCLE": "Trend remains strong but crowding, price extension, or narrow breadth indicate late-cycle risk.",
        "CONTRACTION": "Trend or liquidity is deteriorating enough to describe a contraction phase.",
        "UNKNOWN": "Inputs are insufficient or mixed; phase should remain under observation.",
    }
    return labels.get(normalize_market_phase(phase), labels["UNKNOWN"])
