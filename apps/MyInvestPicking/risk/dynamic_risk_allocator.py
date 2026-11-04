from __future__ import annotations

from typing import Any


REGIME_BUDGETS = {
    "ignored": {
        "max_position_per_stock": 0.12,
        "max_industry_weight": 0.35,
        "target_exposure": 1.00,
        "drawdown_threshold": 1.00,
        "max_cluster_weight": 0.50,
        "max_beijing_weight": 0.20,
    },
    "trend": {
        "max_position_per_stock": 0.12,
        "max_industry_weight": 0.35,
        "target_exposure": 0.95,
        "drawdown_threshold": 0.10,
        "max_cluster_weight": 0.50,
        "max_beijing_weight": 0.20,
    },
    "range": {
        "max_position_per_stock": 0.10,
        "max_industry_weight": 0.30,
        "target_exposure": 0.85,
        "drawdown_threshold": 0.08,
        "max_cluster_weight": 0.45,
        "max_beijing_weight": 0.15,
    },
    "high_vol": {
        "max_position_per_stock": 0.07,
        "max_industry_weight": 0.25,
        "target_exposure": 0.65,
        "drawdown_threshold": 0.06,
        "max_cluster_weight": 0.35,
        "max_beijing_weight": 0.08,
    },
    "crash": {
        "max_position_per_stock": 0.05,
        "max_industry_weight": 0.20,
        "target_exposure": 0.40,
        "drawdown_threshold": 0.04,
        "max_cluster_weight": 0.25,
        "max_beijing_weight": 0.03,
    },
}


def allocate_dynamic_risk_budget(market_regime: dict[str, Any]) -> dict[str, Any]:
    state = str(market_regime.get("state") or "range")
    budget = dict(REGIME_BUDGETS.get(state, REGIME_BUDGETS["range"]))
    budget["regime"] = state
    budget["confidence"] = float(market_regime.get("confidence") or 0)
    return budget
