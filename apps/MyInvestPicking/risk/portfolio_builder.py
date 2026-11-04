from __future__ import annotations

from typing import Any

from risk.drawdown_guard import apply_drawdown_guard, estimate_portfolio_drawdown
from risk.exposure_risk import calculate_industry_exposure, cap_industry_exposure


DEFAULT_MAX_POSITION_PER_STOCK = 0.10
DEFAULT_MAX_INDUSTRY_WEIGHT = 0.30
DEFAULT_DRAWDOWN_THRESHOLD = 0.08
DEFAULT_MAX_BEIJING_WEIGHT = 0.15


def build_portfolio(
    picks: list[dict[str, Any]],
    max_position_per_stock: float = DEFAULT_MAX_POSITION_PER_STOCK,
    max_industry_weight: float = DEFAULT_MAX_INDUSTRY_WEIGHT,
    drawdown_threshold: float = DEFAULT_DRAWDOWN_THRESHOLD,
    target_exposure: float = 1.0,
    correlation_clusters: list[dict[str, Any]] | None = None,
    max_cluster_weight: float = 0.45,
    max_beijing_weight: float = DEFAULT_MAX_BEIJING_WEIGHT,
) -> dict[str, Any]:
    if not picks:
        return _empty_portfolio(
            max_position_per_stock,
            max_industry_weight,
            drawdown_threshold,
            target_exposure,
            max_beijing_weight,
        )

    positions = _initial_score_weighted_positions(picks)
    positions = _cap_position_weights(positions, max_position_per_stock)
    positions, industry_exposure = cap_industry_exposure(positions, max_industry_weight)
    positions, cluster_exposure = _cap_cluster_exposure(
        positions,
        correlation_clusters or [],
        max_cluster_weight,
    )
    positions, exchange_exposure = _cap_beijing_exposure(positions, max_beijing_weight)
    positions = _fit_to_target_exposure(
        positions,
        target_exposure=target_exposure,
        max_position_per_stock=max_position_per_stock,
        max_industry_weight=max_industry_weight,
        correlation_clusters=correlation_clusters or [],
        max_cluster_weight=max_cluster_weight,
        max_beijing_weight=max_beijing_weight,
    )

    estimated_drawdown = estimate_portfolio_drawdown(positions)
    positions, drawdown_guard = apply_drawdown_guard(
        positions,
        estimated_drawdown=estimated_drawdown,
        threshold=drawdown_threshold,
    )

    positions = _round_positions(positions)
    positions = _trim_rounding_excess(positions, target_exposure)
    industry_exposure = calculate_industry_exposure(positions)
    exchange_exposure = calculate_exchange_exposure(positions)
    invested_weight = round(sum(position["weight"] for position in positions), 6)
    cash_weight = round(max(0.0, 1.0 - invested_weight), 6)
    expected_volatility = round(
        sum(
            position["weight"] * float((position.get("metrics") or {}).get("volatility_20d") or 0)
            for position in positions
        ),
        6,
    )

    return {
        "positions": positions,
        "risk": {
            "max_position_per_stock": max_position_per_stock,
            "max_industry_weight": max_industry_weight,
            "max_cluster_weight": max_cluster_weight,
            "max_beijing_weight": max_beijing_weight,
            "target_exposure": target_exposure,
            "portfolio_exposure": invested_weight,
            "industry_exposure": industry_exposure,
            "exchange_exposure": exchange_exposure,
            "cluster_exposure": cluster_exposure,
            "estimated_drawdown": estimated_drawdown,
            "drawdown_guard": drawdown_guard,
            "expected_volatility": expected_volatility,
            "cash_weight": cash_weight,
            "risk_level": _risk_level(estimated_drawdown, drawdown_threshold),
        },
    }


def _initial_score_weighted_positions(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored = []
    for pick in picks:
        weight_score = pick.get("final_score") or pick.get("score") or 0
        scored.append((pick, max(float(weight_score), 0.0)))

    total_score = sum(score for _, score in scored)
    if total_score <= 0:
        base_weight = 1.0 / len(scored)
        return [dict(pick, weight=base_weight) for pick, _ in scored]

    return [dict(pick, weight=score / total_score) for pick, score in scored]


def _cap_position_weights(
    positions: list[dict[str, Any]],
    max_position_per_stock: float,
) -> list[dict[str, Any]]:
    capped = [dict(position) for position in positions]
    for _ in range(10):
        excess = 0.0
        receivers = []
        for position in capped:
            weight = float(position["weight"])
            if weight > max_position_per_stock:
                excess += weight - max_position_per_stock
                position["weight"] = max_position_per_stock
            elif weight < max_position_per_stock:
                receivers.append(position)

        if excess <= 1e-12 or not receivers:
            break

        receiver_total = sum(float(position["weight"]) for position in receivers)
        if receiver_total <= 0:
            spread = excess / len(receivers)
            for position in receivers:
                position["weight"] += spread
        else:
            for position in receivers:
                position["weight"] += excess * float(position["weight"]) / receiver_total

    return capped


def _round_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rounded = []
    for position in positions:
        item = dict(position)
        item["weight"] = round(float(item.get("weight") or 0), 6)
        rounded.append(item)
    return rounded


def _trim_rounding_excess(
    positions: list[dict[str, Any]],
    target_exposure: float,
) -> list[dict[str, Any]]:
    exposure = round(sum(position["weight"] for position in positions), 6)
    excess = round(exposure - target_exposure, 6)
    if excess <= 0:
        return positions

    adjusted = [dict(position) for position in positions]
    for position in reversed(adjusted):
        if position["weight"] >= excess:
            position["weight"] = round(position["weight"] - excess, 6)
            break
    return adjusted


def _cap_cluster_exposure(
    positions: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    max_cluster_weight: float,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    adjusted = [dict(position) for position in positions]
    cluster_exposure = {}
    for cluster in clusters:
        codes = set(cluster.get("codes", []))
        exposure = sum(float(position.get("weight") or 0) for position in adjusted if position["code"] in codes)
        if exposure > max_cluster_weight and exposure > 0:
            scale = max_cluster_weight / exposure
            for position in adjusted:
                if position["code"] in codes:
                    position["weight"] = float(position["weight"]) * scale
            exposure = max_cluster_weight
        cluster_exposure[str(cluster.get("id"))] = round(exposure, 6)
    return adjusted, cluster_exposure


def calculate_exchange_exposure(positions: list[dict[str, Any]]) -> dict[str, float]:
    exposure: dict[str, float] = {}
    for position in positions:
        exchange = _exchange_code(position)
        exposure[exchange] = exposure.get(exchange, 0.0) + float(position.get("weight") or 0)
    return {exchange: round(weight, 6) for exchange, weight in sorted(exposure.items())}


def _cap_beijing_exposure(
    positions: list[dict[str, Any]],
    max_beijing_weight: float,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    adjusted = [dict(position) for position in positions]
    beijing_weight = sum(
        float(position.get("weight") or 0)
        for position in adjusted
        if _exchange_code(position) == "BJ"
    )
    if beijing_weight <= max_beijing_weight or beijing_weight <= 0:
        return adjusted, calculate_exchange_exposure(adjusted)

    scale = max_beijing_weight / beijing_weight
    for position in adjusted:
        if _exchange_code(position) == "BJ":
            position["weight"] = float(position["weight"]) * scale
    return adjusted, calculate_exchange_exposure(adjusted)


def _exchange_code(position: dict[str, Any]) -> str:
    code = str(position.get("code") or "")
    if "." not in code:
        return "Unknown"
    return code.rsplit(".", 1)[-1]


def _fit_to_target_exposure(
    positions: list[dict[str, Any]],
    target_exposure: float,
    max_position_per_stock: float,
    max_industry_weight: float,
    correlation_clusters: list[dict[str, Any]],
    max_cluster_weight: float,
    max_beijing_weight: float,
) -> list[dict[str, Any]]:
    current = sum(float(position.get("weight") or 0) for position in positions)
    if current <= 0:
        return positions
    if current > target_exposure:
        scale = target_exposure / current
        return [dict(position, weight=float(position["weight"]) * scale) for position in positions]

    adjusted = [dict(position) for position in positions]
    cluster_by_code = _cluster_codes_by_position(correlation_clusters)
    for _ in range(20):
        current = sum(float(position.get("weight") or 0) for position in adjusted)
        shortfall = target_exposure - current
        if shortfall <= 1e-9:
            break

        capacities = _position_capacities(
            adjusted,
            max_position_per_stock=max_position_per_stock,
            max_industry_weight=max_industry_weight,
            cluster_by_code=cluster_by_code,
            max_cluster_weight=max_cluster_weight,
            max_beijing_weight=max_beijing_weight,
        )
        receivers = [
            (index, capacity)
            for index, capacity in capacities.items()
            if capacity > 1e-9
        ]
        if not receivers:
            break

        receiver_score = sum(
            max(float(adjusted[index].get("weight") or 0), 1e-9)
            for index, _ in receivers
        )
        distributed = 0.0
        for index, capacity in receivers:
            base = max(float(adjusted[index].get("weight") or 0), 1e-9)
            addition = min(capacity, shortfall * base / receiver_score)
            if addition <= 0:
                continue
            adjusted[index]["weight"] = float(adjusted[index].get("weight") or 0) + addition
            distributed += addition
        if distributed <= 1e-9:
            break

    return adjusted


def _position_capacities(
    positions: list[dict[str, Any]],
    max_position_per_stock: float,
    max_industry_weight: float,
    cluster_by_code: dict[str, list[str]],
    max_cluster_weight: float,
    max_beijing_weight: float,
) -> dict[int, float]:
    industry_exposure = calculate_industry_exposure(positions)
    exchange_exposure = calculate_exchange_exposure(positions)
    cluster_exposure = _calculate_cluster_exposure(positions, cluster_by_code)
    capacities: dict[int, float] = {}
    for index, position in enumerate(positions):
        weight = float(position.get("weight") or 0)
        industry = str(position.get("industry") or "Unknown")
        exchange = _exchange_code(position)
        code = str(position.get("code") or "")
        capacity = max_position_per_stock - weight
        capacity = min(
            capacity,
            max_industry_weight - float(industry_exposure.get(industry, 0)),
        )
        if exchange == "BJ":
            capacity = min(
                capacity,
                max_beijing_weight - float(exchange_exposure.get("BJ", 0)),
            )
        for cluster_id in cluster_by_code.get(code, []):
            capacity = min(
                capacity,
                max_cluster_weight - float(cluster_exposure.get(cluster_id, 0)),
            )
        capacities[index] = max(0.0, capacity)
    return capacities


def _cluster_codes_by_position(
    clusters: list[dict[str, Any]],
) -> dict[str, list[str]]:
    cluster_by_code: dict[str, list[str]] = {}
    for cluster in clusters:
        cluster_id = str(cluster.get("id"))
        for code in cluster.get("codes", []):
            cluster_by_code.setdefault(str(code), []).append(cluster_id)
    return cluster_by_code


def _calculate_cluster_exposure(
    positions: list[dict[str, Any]],
    cluster_by_code: dict[str, list[str]],
) -> dict[str, float]:
    exposure: dict[str, float] = {}
    for position in positions:
        code = str(position.get("code") or "")
        weight = float(position.get("weight") or 0)
        for cluster_id in cluster_by_code.get(code, []):
            exposure[cluster_id] = exposure.get(cluster_id, 0.0) + weight
    return exposure


def _risk_level(estimated_drawdown: float, threshold: float) -> str:
    if estimated_drawdown >= threshold:
        return "high"
    if estimated_drawdown >= threshold * 0.6:
        return "medium"
    return "low"


def _empty_portfolio(
    max_position_per_stock: float,
    max_industry_weight: float,
    drawdown_threshold: float,
    target_exposure: float,
    max_beijing_weight: float,
) -> dict[str, Any]:
    return {
        "positions": [],
        "risk": {
            "max_position_per_stock": max_position_per_stock,
            "max_industry_weight": max_industry_weight,
            "max_cluster_weight": 0.45,
            "max_beijing_weight": max_beijing_weight,
            "target_exposure": target_exposure,
            "portfolio_exposure": 0.0,
            "industry_exposure": {},
            "exchange_exposure": {},
            "cluster_exposure": {},
            "estimated_drawdown": 0.0,
            "drawdown_guard": {
                "triggered": False,
                "threshold": drawdown_threshold,
                "scale": 1.0,
            },
            "expected_volatility": 0.0,
            "cash_weight": 1.0,
            "risk_level": "low",
        },
    }
