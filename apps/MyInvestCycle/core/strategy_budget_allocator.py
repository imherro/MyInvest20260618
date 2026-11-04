from __future__ import annotations

from typing import Mapping

from core.strategy_filter import load_strategy_policy


def _strategy_penalty(policy: Mapping[str, Mapping[str, object]], strategy: str) -> float:
    strategies = policy.get("strategies", {})
    strategy_policy = strategies.get(strategy, {}) if isinstance(strategies, Mapping) else {}
    if not isinstance(strategy_policy, Mapping):
        return 0.0
    return float(strategy_policy.get("risk_penalty", 0.0))


def allocate_strategy_budget(
    portfolio_allocation: Mapping[str, object],
    enabled_strategies: list[str],
    *,
    policy: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    resolved_policy = load_strategy_policy() if policy is None else policy
    strategy_allocation = portfolio_allocation.get("strategy_allocation", {})
    if not isinstance(strategy_allocation, Mapping):
        raise ValueError("portfolio_allocation.strategy_allocation must be a mapping")

    adjusted: dict[str, float] = {}
    reasoning: dict[str, str] = {}
    for strategy in enabled_strategies:
        base_weight = float(strategy_allocation.get(strategy, 0.0))
        penalty = _strategy_penalty(resolved_policy, strategy)
        adjusted_weight = base_weight * (1.0 - penalty)
        if adjusted_weight > 0.0:
            adjusted[strategy] = adjusted_weight
            reasoning[strategy] = f"base_weight={base_weight:.4f}, risk_penalty={penalty:.2f}"

    total_adjusted = sum(adjusted.values())
    if total_adjusted <= 0.0:
        raise ValueError("No positive enabled strategy budget after routing")

    strategy_budget = {
        strategy: round(weight / total_adjusted, 6) for strategy, weight in adjusted.items()
    }
    drift = round(1.0 - sum(strategy_budget.values()), 6)
    if strategy_budget and drift:
        last_key = next(reversed(strategy_budget))
        strategy_budget[last_key] = round(strategy_budget[last_key] + drift, 6)

    total_exposure = float(portfolio_allocation["total_exposure"])
    strategy_capital_budget = {
        strategy: round(weight * total_exposure, 6) for strategy, weight in strategy_budget.items()
    }

    return {
        "strategy_budget": strategy_budget,
        "strategy_capital_budget": strategy_capital_budget,
        "reasoning": reasoning,
    }
