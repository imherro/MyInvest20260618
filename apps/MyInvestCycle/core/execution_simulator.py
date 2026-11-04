from __future__ import annotations

from typing import Mapping

from core.execution_policy import load_execution_policy
from core.order_intent_builder import build_execution_intent, build_simulated_orders


def simulate_execution_layer(
    strategy_route: Mapping[str, object],
    *,
    policy: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    resolved_policy = load_execution_policy() if policy is None else policy
    execution_intent = build_execution_intent(strategy_route, policy=resolved_policy)
    simulated_orders = build_simulated_orders(
        strategy_route,
        execution_intent,
        policy=resolved_policy,
    )

    return {
        "as_of": strategy_route.get("as_of"),
        "regime": strategy_route["regime"],
        "risk_score": strategy_route["risk_score"],
        "portfolio_exposure": strategy_route["total_exposure"],
        "strategy_mode": execution_intent["execution_mode"],
        "execution_intent": execution_intent,
        "simulated_orders": simulated_orders,
        "constraints": {
            "simulated_only": True,
            "no_real_orders": True,
            "no_broker_connection": True,
            "order_count": len(simulated_orders),
        },
    }
