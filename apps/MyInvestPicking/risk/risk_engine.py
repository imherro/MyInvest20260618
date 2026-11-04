from __future__ import annotations

from typing import Any

from risk.portfolio_builder import build_portfolio


def build_risk_managed_portfolio(
    picks: list[dict[str, Any]],
    risk_budget: dict[str, Any] | None = None,
    correlation_clusters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    budget = risk_budget or {}
    return build_portfolio(
        picks,
        max_position_per_stock=float(budget.get("max_position_per_stock", 0.10)),
        max_industry_weight=float(budget.get("max_industry_weight", 0.30)),
        drawdown_threshold=float(budget.get("drawdown_threshold", 0.08)),
        target_exposure=float(budget.get("target_exposure", 1.0)),
        correlation_clusters=correlation_clusters,
        max_cluster_weight=float(budget.get("max_cluster_weight", 0.45)),
        max_beijing_weight=float(budget.get("max_beijing_weight", 0.15)),
    )
