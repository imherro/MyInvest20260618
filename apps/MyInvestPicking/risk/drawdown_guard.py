from __future__ import annotations

from typing import Any


def estimate_portfolio_drawdown(positions: list[dict[str, Any]]) -> float:
    weighted_volatility = sum(
        float(position.get("weight") or 0)
        * float((position.get("metrics") or {}).get("volatility_20d") or 0)
        for position in positions
    )
    return round(weighted_volatility * 2.0, 6)


def apply_drawdown_guard(
    positions: list[dict[str, Any]],
    estimated_drawdown: float,
    threshold: float,
    min_exposure: float = 0.4,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if estimated_drawdown <= threshold or estimated_drawdown <= 0:
        return positions, {
            "triggered": False,
            "threshold": threshold,
            "scale": 1.0,
        }

    scale = max(min(threshold / estimated_drawdown, 1.0), min_exposure)
    adjusted = [dict(position, weight=float(position["weight"]) * scale) for position in positions]
    return adjusted, {
        "triggered": True,
        "threshold": threshold,
        "scale": round(scale, 6),
    }
