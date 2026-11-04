from __future__ import annotations

from typing import Mapping

from core.etf_universe_builder import ETF_UNIVERSE
from core.risk_score_engine import _clip


STYLE_TO_ETF_WEIGHTS: dict[str, dict[str, float]] = {
    "growth": {"159915.SZ": 1.0},
    "small_cap": {"510500.SH": 1.0},
    "value": {"510300.SH": 1.0},
    "dividend": {"510880.SH": 1.0},
    "low_vol": {"510880.SH": 1.0},
}
CASH_PROXY_CODE = "511880.SH"


def _etf_lookup() -> dict[str, dict[str, object]]:
    return {str(item["code"]): dict(item) for item in ETF_UNIVERSE}


def _normalize(weights: Mapping[str, float]) -> dict[str, float]:
    positive = {code: max(0.0, float(weight)) for code, weight in weights.items()}
    total = sum(positive.values())
    if total <= 0:
        return {}
    normalized = {code: value / total for code, value in positive.items()}
    rounded = {code: round(value, 6) for code, value in normalized.items()}
    drift = round(1.0 - sum(rounded.values()), 6)
    if drift:
        largest = max(rounded, key=rounded.get)
        rounded[largest] = round(rounded[largest] + drift, 6)
    return rounded


def build_macro_style_etf_allocation(
    style_allocation: Mapping[str, float],
    *,
    target_exposure: float,
    cash_proxy_code: str = CASH_PROXY_CODE,
) -> dict[str, object]:
    """ETF layer: only maps style weights into ETF weights."""

    exposure = _clip(float(target_exposure))
    weights: dict[str, float] = {}
    style_to_etf: dict[str, dict[str, float]] = {}
    for style, style_weight in style_allocation.items():
        mapping = STYLE_TO_ETF_WEIGHTS.get(str(style), {})
        if not mapping:
            continue
        style_to_etf[str(style)] = dict(mapping)
        for code, mapping_weight in mapping.items():
            weights[code] = weights.get(code, 0.0) + exposure * float(style_weight) * float(mapping_weight)

    cash_weight = max(0.0, 1.0 - exposure)
    if cash_weight > 0:
        weights[cash_proxy_code] = weights.get(cash_proxy_code, 0.0) + cash_weight

    allocation = _normalize(weights)
    lookup = _etf_lookup()
    return {
        "engine": "Macro Style ETF Allocator M2.1",
        "target_exposure": round(exposure, 6),
        "cash_proxy_code": cash_proxy_code,
        "style_to_etf": style_to_etf,
        "etf_allocation": allocation,
        "etf_details": [
            {
                "code": code,
                "name": lookup.get(code, {}).get("name", code),
                "bucket": lookup.get(code, {}).get("bucket"),
                "risk_tier": lookup.get(code, {}).get("risk_tier"),
                "weight": weight,
            }
            for code, weight in sorted(allocation.items(), key=lambda item: item[1], reverse=True)
        ],
        "constraints": {
            "etf_implements_mapping_only": True,
            "no_single_stock_selection": True,
            "no_trade_execution": True,
            "cash_is_residual_exposure_buffer": True,
        },
    }
