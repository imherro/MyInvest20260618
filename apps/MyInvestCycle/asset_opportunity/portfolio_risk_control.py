from __future__ import annotations

from dataclasses import dataclass


REBALANCE_STEPS = (20, 40, 60)
TRANSACTION_COSTS = (0.0, 0.001, 0.002)
MINIMUM_HOLDING_DAYS = 20


@dataclass(frozen=True)
class RiskControlScenario:
    label: str
    rebalance_step: int
    transaction_cost: float
    minimum_holding_days: int
    purpose: str

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "rebalance_step": self.rebalance_step,
            "transaction_cost": self.transaction_cost,
            "minimum_holding_days": self.minimum_holding_days,
            "purpose": self.purpose,
        }


def cost_label(cost: float) -> str:
    return f"{int(round(cost * 10000))}bp"


def scenario_label(step: int, cost: float, minimum_holding_days: int) -> str:
    return f"step{step}_cost{cost_label(cost)}_min{minimum_holding_days}"


def default_risk_control_scenarios() -> list[RiskControlScenario]:
    scenarios: list[RiskControlScenario] = []
    for step in REBALANCE_STEPS:
        for cost in TRANSACTION_COSTS:
            scenarios.append(
                RiskControlScenario(
                    label=scenario_label(step, cost, MINIMUM_HOLDING_DAYS),
                    rebalance_step=step,
                    transaction_cost=cost,
                    minimum_holding_days=MINIMUM_HOLDING_DAYS,
                    purpose="fixed rebalance and cost sensitivity",
                )
            )
    scenarios.append(
        RiskControlScenario(
            label=scenario_label(20, 0.001, 0),
            rebalance_step=20,
            transaction_cost=0.001,
            minimum_holding_days=0,
            purpose="baseline without minimum holding filter",
        )
    )
    return scenarios


def concentration_level(max_theme_share: float | None) -> str:
    if max_theme_share is None:
        return "unknown"
    if max_theme_share >= 0.67:
        return "high"
    if max_theme_share >= 0.5:
        return "elevated"
    return "diversified"


def attach_concentration_level(theme_concentration: dict[str, object]) -> dict[str, object]:
    average = theme_concentration.get("average_max_theme_share")
    latest = theme_concentration.get("latest_theme_shares")
    latest_max = None
    if isinstance(latest, dict) and latest:
        latest_max = max(float(value) for value in latest.values())
    return {
        **theme_concentration,
        "average_concentration_level": concentration_level(float(average) if average is not None else None),
        "latest_concentration_level": concentration_level(latest_max),
        "monitor_only": True,
    }
