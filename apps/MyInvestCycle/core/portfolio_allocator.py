from __future__ import annotations

from typing import Mapping

from core.capital_controller import build_capital_control, load_portfolio_policy, regime_portfolio_policy


def _extract_risk_decision(risk_output: Mapping[str, object]) -> Mapping[str, object]:
    decision = risk_output.get("decision")
    if isinstance(decision, Mapping):
        return decision
    return risk_output


def normalize_strategy_allocation(strategy_allocation: Mapping[str, object]) -> dict[str, float]:
    total = sum(float(weight) for weight in strategy_allocation.values())
    if total <= 0.0:
        raise ValueError("strategy_allocation weights must be positive")
    normalized = {str(strategy): round(float(weight) / total, 6) for strategy, weight in strategy_allocation.items()}
    drift = round(1.0 - sum(normalized.values()), 6)
    if normalized and drift:
        last_key = next(reversed(normalized))
        normalized[last_key] = round(normalized[last_key] + drift, 6)
    return normalized


def build_portfolio_allocation(
    risk_output: Mapping[str, object],
    *,
    policy: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    resolved_policy = load_portfolio_policy() if policy is None else policy
    risk_decision = _extract_risk_decision(risk_output)
    regime = str(risk_decision["regime"])
    regime_policy = regime_portfolio_policy(resolved_policy, regime)
    capital_control = build_capital_control(risk_decision, policy=resolved_policy)
    strategy_allocation = normalize_strategy_allocation(regime_policy["strategy_allocation"])
    total_exposure = float(capital_control["total_exposure"])
    strategy_capital_allocation = {
        strategy: round(weight * total_exposure, 6) for strategy, weight in strategy_allocation.items()
    }

    source_input = risk_output.get("input") if isinstance(risk_output.get("input"), Mapping) else {}
    return {
        "as_of": source_input.get("as_of"),
        "regime": regime,
        "risk_level": risk_decision.get("risk_level"),
        "risk_score": risk_decision["risk_score"],
        "total_exposure": capital_control["total_exposure"],
        "cash_ratio": capital_control["cash_ratio"],
        "strategy_allocation": strategy_allocation,
        "strategy_capital_allocation": strategy_capital_allocation,
        "capital_control": capital_control,
        "constraints": {
            **capital_control["constraints"],
            "strategy_allocation_sum": round(sum(strategy_allocation.values()), 6),
            "strategy_capital_sum": round(sum(strategy_capital_allocation.values()), 6),
            "no_stock_selection": True,
        },
    }
