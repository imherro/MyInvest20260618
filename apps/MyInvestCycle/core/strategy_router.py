from __future__ import annotations

from typing import Mapping

from core.strategy_budget_allocator import allocate_strategy_budget
from core.strategy_filter import filter_strategies, load_strategy_policy


def build_strategy_route(
    portfolio_allocation: Mapping[str, object],
    *,
    policy: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    resolved_policy = load_strategy_policy() if policy is None else policy
    filtered = filter_strategies(portfolio_allocation, policy=resolved_policy)
    budget = allocate_strategy_budget(
        portfolio_allocation,
        filtered["enabled_strategies"],
        policy=resolved_policy,
    )
    strategy_budget = budget["strategy_budget"]
    strategy_capital_budget = budget["strategy_capital_budget"]

    return {
        "as_of": portfolio_allocation.get("as_of"),
        "regime": portfolio_allocation["regime"],
        "risk_score": portfolio_allocation["risk_score"],
        "total_exposure": portfolio_allocation["total_exposure"],
        "enabled_strategies": filtered["enabled_strategies"],
        "disabled_strategies": filtered["disabled_strategies"],
        "strategy_budget": strategy_budget,
        "strategy_capital_budget": strategy_capital_budget,
        "disabled_reason": filtered["disabled_reason"],
        "reasoning": budget["reasoning"],
        "policy_context": {
            "enabled": filtered["policy_enabled"],
            "disabled": filtered["policy_disabled"],
            "risk_gate_disabled": filtered["risk_gate_disabled"],
        },
        "constraints": {
            "strategy_budget_sum": round(sum(strategy_budget.values()), 6),
            "strategy_capital_sum": round(sum(strategy_capital_budget.values()), 6),
            "no_trade_execution": True,
        },
    }
