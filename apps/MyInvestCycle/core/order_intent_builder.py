from __future__ import annotations

from typing import Mapping

from core.execution_policy import list_policy_value, load_execution_policy, regime_execution_policy


def build_execution_intent(
    strategy_route: Mapping[str, object],
    *,
    policy: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    resolved_policy = load_execution_policy() if policy is None else policy
    regime = str(strategy_route["regime"])
    risk_score = float(strategy_route["risk_score"])
    regime_policy = regime_execution_policy(resolved_policy, regime)
    risk_policy = resolved_policy.get("risk", {})

    allowed_actions = list_policy_value(regime_policy, "allow")
    forbidden_actions = list_policy_value(regime_policy, "forbid")
    block_threshold = float(risk_policy.get("block_new_exposure_threshold", 1.0))
    block_new_exposure = risk_score > block_threshold

    if block_new_exposure:
        for action in ("open_new_position", "increase_exposure"):
            if action not in forbidden_actions:
                forbidden_actions.append(action)
            if action in allowed_actions:
                allowed_actions.remove(action)

    return {
        "regime": regime,
        "risk_score": round(risk_score, 6),
        "execution_mode": str(regime_policy["execution_mode"]),
        "allowed_actions": allowed_actions,
        "forbidden_actions": forbidden_actions,
        "constraints": {
            "simulated_only": True,
            "no_real_orders": True,
            "block_new_exposure": block_new_exposure,
        },
    }


def build_simulated_orders(
    strategy_route: Mapping[str, object],
    execution_intent: Mapping[str, object],
    *,
    policy: Mapping[str, Mapping[str, object]] | None = None,
) -> list[dict[str, object]]:
    resolved_policy = load_execution_policy() if policy is None else policy
    regime = str(strategy_route["regime"])
    regime_policy = regime_execution_policy(resolved_policy, regime)
    risk_policy = resolved_policy.get("risk", {})
    allowed_actions = set(execution_intent.get("allowed_actions", []))
    total_exposure = float(strategy_route["total_exposure"])
    reference_exposure = float(regime_policy["reference_exposure"])
    min_weight_change = float(risk_policy.get("min_weight_change", 0.01))
    exposure_delta = total_exposure - reference_exposure

    orders: list[dict[str, object]] = []
    if exposure_delta <= -min_weight_change and "reduce_exposure" in allowed_actions:
        orders.append(
            {
                "action": "reduce_exposure",
                "asset_class": "equity",
                "weight_change": round(exposure_delta, 6),
                "reason": f"{regime} regime risk control",
                "simulated": True,
            }
        )
    elif exposure_delta >= min_weight_change and "increase_exposure" in allowed_actions:
        orders.append(
            {
                "action": "increase_exposure",
                "asset_class": "equity",
                "weight_change": round(exposure_delta, 6),
                "reason": f"{regime} regime exposure alignment",
                "simulated": True,
            }
        )

    if "rebalance_strategy" in allowed_actions:
        capital_budget = strategy_route.get("strategy_capital_budget", {})
        if not isinstance(capital_budget, Mapping):
            raise ValueError("strategy_route.strategy_capital_budget must be a mapping")
        for strategy, target_weight in capital_budget.items():
            orders.append(
                {
                    "action": "rebalance_strategy",
                    "asset_class": "strategy_budget",
                    "strategy": str(strategy),
                    "target_weight": round(float(target_weight), 6),
                    "reason": "strategy routing budget",
                    "simulated": True,
                }
            )

    return orders
