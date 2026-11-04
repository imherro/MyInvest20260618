from __future__ import annotations

from dataclasses import dataclass


OPPORTUNITY_STATES = (
    "EARLY_RECOVERY",
    "BULL_EXPANSION",
    "STRUCTURAL_ROTATION",
    "LATE_BULL",
    "DEFENSIVE_REPAIR",
    "UNKNOWN",
)

RISK_STATES = (
    "LOW_RISK",
    "NORMAL",
    "CROWDED",
    "HIGH_RISK",
    "UNKNOWN",
)


@dataclass(frozen=True)
class OpportunityRiskResult:
    opportunity_state: str
    risk_state: str
    combined_state: str
    evidence: tuple[str, ...]
    metrics: dict[str, object]
    interpretation: str


def normalize_opportunity_state(value: object) -> str:
    text = str(value or "UNKNOWN")
    return text if text in OPPORTUNITY_STATES else "UNKNOWN"


def normalize_risk_state(value: object) -> str:
    text = str(value or "UNKNOWN")
    return text if text in RISK_STATES else "UNKNOWN"
