from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from asset_opportunity.asset_proxy_schema import AssetProxyRecord, ResearchProxy
from asset_opportunity.asset_registry import DEFAULT_REGISTRY_PATH, read_asset_registry
from config import BASE_DIR, DATA_DIR


DEFAULT_PROXY_REGISTRY_PATH = DATA_DIR / "asset_proxy_registry.json"


PROXY_MAP: dict[str, ResearchProxy] = {
    "512000.SH": ResearchProxy("801790.SI", "非银金融", "index", "Tushare index_daily SW2021 L1"),
    "512800.SH": ResearchProxy("801780.SI", "银行", "index", "Tushare index_daily SW2021 L1"),
    "512690.SH": ResearchProxy("801120.SI", "食品饮料", "index", "Tushare index_daily SW2021 L1"),
    "512480.SH": ResearchProxy("801080.SI", "电子", "index", "Tushare index_daily SW2021 L1"),
    "512170.SH": ResearchProxy("801150.SI", "医药生物", "index", "Tushare index_daily SW2021 L1"),
    "512660.SH": ResearchProxy("801740.SI", "国防军工", "index", "Tushare index_daily SW2021 L1"),
    "515790.SH": ResearchProxy("801730.SI", "电力设备", "index", "Tushare index_daily SW2021 L1"),
    "516160.SH": ResearchProxy("801730.SI", "电力设备", "index", "Tushare index_daily SW2021 L1"),
    "515000.SH": ResearchProxy("801750.SI", "计算机", "index", "Tushare index_daily SW2021 L1"),
    "588000.SH": ResearchProxy("801080.SI", "电子", "index", "Tushare index_daily SW2021 L1"),
}


def _project_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def _record_for_asset(asset) -> AssetProxyRecord:
    proxy = PROXY_MAP.get(asset.code)
    if proxy is None:
        return AssetProxyRecord(
            asset_code=asset.code,
            asset_name=asset.name,
            asset_type=asset.type,
            asset_category=asset.category,
            mapping_method="direct_etf_history_only",
            research_proxy=None,
            enabled=asset.enabled,
            notes="No long-history proxy assigned in V3.1.2; use real ETF history only.",
        )
    return AssetProxyRecord(
        asset_code=asset.code,
        asset_name=asset.name,
        asset_type=asset.type,
        asset_category=asset.category,
        mapping_method="research_only",
        research_proxy=proxy,
        enabled=asset.enabled,
        notes="Research proxy is for long-history opportunity research only; it does not fabricate ETF tradability.",
    )


def build_asset_proxy_registry(
    *,
    asset_registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, object]:
    assets = read_asset_registry(asset_registry_path)
    mappings = [_record_for_asset(asset) for asset in assets]
    with_proxy = [record for record in mappings if record.research_proxy is not None and record.enabled]
    proxy_codes = [record.research_proxy.code for record in with_proxy if record.research_proxy]
    return {
        "metadata": {
            "engine": "V3.1.2 Asset Research Proxy Layer",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "asset_registry": _project_path(asset_registry_path),
            "ETF_assets": len([asset for asset in assets if asset.enabled]),
            "with_proxy": len(with_proxy),
            "proxy_count": len(set(proxy_codes)),
            "proxy_usage_counts": dict(Counter(proxy_codes)),
            "purpose": "Separate tradable ETF assets from long-history research proxies.",
        },
        "mappings": [record.to_dict() for record in mappings],
        "constraints": {
            "etf_and_proxy_separated": True,
            "research_proxy_only": True,
            "does_not_fabricate_etf_history": True,
            "no_opportunity_score": True,
            "no_ranking": True,
            "no_allocation": True,
            "no_backtest": True,
            "no_trade_execution": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def write_asset_proxy_registry(
    payload: Mapping[str, object] | None = None,
    output_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
) -> Path:
    path = Path(output_path)
    registry = dict(payload or build_asset_proxy_registry())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_asset_proxy_registry(path: str | Path = DEFAULT_PROXY_REGISTRY_PATH) -> list[AssetProxyRecord]:
    registry_path = Path(path)
    if not registry_path.exists():
        payload = build_asset_proxy_registry()
    else:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    rows = payload.get("mappings") or []
    return [AssetProxyRecord.from_mapping(row) for row in rows if isinstance(row, Mapping)]
