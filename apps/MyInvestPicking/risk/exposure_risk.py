from __future__ import annotations

from collections import defaultdict
from typing import Any


def calculate_industry_exposure(positions: list[dict[str, Any]]) -> dict[str, float]:
    exposure: dict[str, float] = defaultdict(float)
    for position in positions:
        industry = position.get("industry") or "Unknown"
        exposure[str(industry)] += float(position.get("weight") or 0)
    return {industry: round(weight, 6) for industry, weight in sorted(exposure.items())}


def cap_industry_exposure(
    positions: list[dict[str, Any]],
    max_industry_weight: float,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    adjusted = [dict(position) for position in positions]
    exposure = calculate_industry_exposure(adjusted)

    for industry, weight in exposure.items():
        if weight <= max_industry_weight or weight <= 0:
            continue

        scale = max_industry_weight / weight
        for position in adjusted:
            if (position.get("industry") or "Unknown") == industry:
                position["weight"] = float(position["weight"]) * scale

    return adjusted, calculate_industry_exposure(adjusted)
