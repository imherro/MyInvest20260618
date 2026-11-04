from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


ALPHA_REGIMES = {"BROAD_BULL", "STRUCTURAL_BULL", "RANGE", "BEAR", "HIGH_CROWDING"}
ALPHA_MODELS = {"trend_following", "rotation_alpha", "mean_reversion", "defensive_quality"}


@dataclass(frozen=True)
class AlphaRegimeDecision:
    date: str
    state_signal_date: str | None
    alpha_regime: str
    recommended_model: str
    structural_state: str
    macro_state: str
    market_structure_state: str
    theme_risk_level: str
    reason: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.alpha_regime not in ALPHA_REGIMES:
            raise ValueError(f"invalid alpha regime: {self.alpha_regime}")
        if self.recommended_model not in ALPHA_MODELS:
            raise ValueError(f"invalid alpha model: {self.recommended_model}")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason"] = list(self.reason)
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AlphaRegimeDecision":
        return cls(
            date=str(payload["date"]),
            state_signal_date=None if payload.get("state_signal_date") is None else str(payload.get("state_signal_date")),
            alpha_regime=str(payload["alpha_regime"]),
            recommended_model=str(payload["recommended_model"]),
            structural_state=str(payload["structural_state"]),
            macro_state=str(payload["macro_state"]),
            market_structure_state=str(payload["market_structure_state"]),
            theme_risk_level=str(payload["theme_risk_level"]),
            reason=tuple(str(item) for item in payload.get("reason", ())),
        )
