from __future__ import annotations

from dataclasses import dataclass


EXPOSURE_LEVELS = ("DEFENSIVE", "LOW", "BALANCED", "HIGH", "OFFENSIVE")


@dataclass(frozen=True)
class ExposureDecision:
    policy_mode: str
    exposure_level: str
    exposure_band: str
    reasons: tuple[str, ...]
    blocked: tuple[str, ...]
    explanation: str


def normalize_exposure_level(value: object) -> str:
    text = str(value or "BALANCED").strip().upper()
    return text if text in EXPOSURE_LEVELS else "BALANCED"


def exposure_rank(level: object) -> int:
    return EXPOSURE_LEVELS.index(normalize_exposure_level(level))
