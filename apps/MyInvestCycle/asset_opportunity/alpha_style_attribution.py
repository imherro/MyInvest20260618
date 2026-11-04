from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from asset_opportunity.asset_registry import read_asset_registry
from asset_opportunity.asset_schema import AssetRecord


def style_bucket_for_asset(asset: AssetRecord) -> str:
    tags = set(asset.tags)
    if tags & {"technology", "growth"}:
        return "growth_technology"
    if "new_energy" in tags:
        return "new_energy"
    if "financial" in tags:
        return "financial_value"
    if "consumer" in tags:
        return "consumer"
    if "healthcare" in tags:
        return "healthcare"
    if "defense" in tags:
        return "defense"
    if tags & {"dividend", "low_vol"}:
        return "dividend_defensive"
    if tags & {"large_cap"}:
        return "value_large"
    if tags & {"mid_cap", "small_cap"}:
        return "mid_small"
    return asset.theme or asset.category


def asset_style_map() -> dict[str, str]:
    return {asset.code: style_bucket_for_asset(asset) for asset in read_asset_registry()}


def style_exposure_for_codes(codes: Iterable[str]) -> dict[str, float]:
    style_map = asset_style_map()
    code_list = [str(code) for code in codes]
    if not code_list:
        return {}
    counts: dict[str, int] = defaultdict(int)
    for code in code_list:
        counts[style_map.get(code, code)] += 1
    return {
        bucket: round(count / len(code_list), 6)
        for bucket, count in sorted(counts.items())
    }


def dominant_style(exposure: dict[str, float]) -> dict[str, object]:
    if not exposure:
        return {"style": None, "share": None, "level": "unknown"}
    style, share = max(exposure.items(), key=lambda item: item[1])
    if share >= 0.67:
        level = "high"
    elif share >= 0.5:
        level = "elevated"
    else:
        level = "diversified"
    return {"style": style, "share": round(float(share), 6), "level": level}
