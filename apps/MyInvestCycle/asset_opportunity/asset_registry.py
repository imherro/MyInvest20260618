from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping

from config import DATA_DIR
from asset_opportunity.asset_schema import AssetRecord


DEFAULT_REGISTRY_PATH = DATA_DIR / "asset_registry.json"


DEFAULT_ASSETS: tuple[AssetRecord, ...] = (
    AssetRecord("510300.SH", "沪深300ETF", "etf", "broad", "Tushare fund_daily", "510300.SH", theme="价值/大盘", tags=("broad", "large_cap")),
    AssetRecord("510500.SH", "中证500ETF", "etf", "broad", "Tushare fund_daily", "510500.SH", theme="中小盘", tags=("broad", "mid_cap")),
    AssetRecord("159915.SZ", "创业板ETF", "etf", "broad", "Tushare fund_daily", "510300.SH", theme="成长/科技", tags=("broad", "growth")),
    AssetRecord("512100.SH", "中证1000ETF", "etf", "broad", "Tushare fund_daily", "510500.SH", theme="小盘", tags=("broad", "small_cap")),
    AssetRecord("510050.SH", "上证50ETF", "etf", "broad", "Tushare fund_daily", "510300.SH", theme="超大盘", tags=("broad", "large_cap")),
    AssetRecord("510880.SH", "红利ETF", "etf", "style", "Tushare fund_daily", "510300.SH", theme="红利", tags=("style", "dividend")),
    AssetRecord("512890.SH", "红利低波ETF", "etf", "style", "Tushare fund_daily", "510300.SH", theme="红利低波", tags=("style", "dividend", "low_vol")),
    AssetRecord("512000.SH", "证券ETF", "etf", "industry", "Tushare fund_daily", "510300.SH", theme="证券", tags=("industry", "financial")),
    AssetRecord("512800.SH", "银行ETF", "etf", "industry", "Tushare fund_daily", "510300.SH", theme="银行", tags=("industry", "financial")),
    AssetRecord("512690.SH", "酒ETF", "etf", "industry", "Tushare fund_daily", "510300.SH", theme="消费", tags=("industry", "consumer")),
    AssetRecord("512480.SH", "半导体ETF", "etf", "industry", "Tushare fund_daily", "510300.SH", theme="半导体", tags=("industry", "technology")),
    AssetRecord("512170.SH", "医疗ETF", "etf", "industry", "Tushare fund_daily", "510300.SH", theme="医疗", tags=("industry", "healthcare")),
    AssetRecord("512660.SH", "军工ETF", "etf", "industry", "Tushare fund_daily", "510300.SH", theme="军工", tags=("industry", "defense")),
    AssetRecord("515790.SH", "光伏ETF", "etf", "industry", "Tushare fund_daily", "510300.SH", theme="光伏", tags=("industry", "new_energy")),
    AssetRecord("516160.SH", "新能源ETF", "etf", "industry", "Tushare fund_daily", "510300.SH", theme="新能源", tags=("industry", "new_energy")),
    AssetRecord("515000.SH", "科技ETF", "etf", "industry", "Tushare fund_daily", "510300.SH", theme="科技", tags=("industry", "technology")),
    AssetRecord("588000.SH", "科创50ETF", "etf", "industry", "Tushare fund_daily", "510300.SH", theme="科创成长", tags=("industry", "technology", "growth")),
)


def _category_counts(assets: Iterable[AssetRecord]) -> dict[str, int]:
    return dict(Counter(asset.category for asset in assets))


def build_asset_registry(assets: Iterable[AssetRecord] = DEFAULT_ASSETS) -> dict[str, object]:
    records = list(assets)
    codes = [asset.code for asset in records]
    if len(codes) != len(set(codes)):
        duplicates = sorted(code for code, count in Counter(codes).items() if count > 1)
        raise ValueError(f"duplicate asset codes: {duplicates}")
    return {
        "metadata": {
            "engine": "V3.1.1 Asset Universe Foundation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "universe": "ETF_ONLY",
            "asset_count": len(records),
            "category_counts": _category_counts(records),
            "purpose": "Asset universe and historical data foundation only; no scoring, no ranking, no allocation.",
        },
        "assets": [asset.to_dict() for asset in records],
        "constraints": {
            "etf_only": True,
            "no_single_stock_selection": True,
            "no_hk_assets": True,
            "no_overseas_assets": True,
            "no_commodity_assets": True,
            "no_leveraged_etf": True,
            "no_cash_or_bond_in_alpha_universe": True,
            "no_opportunity_score": True,
            "no_ranking": True,
            "no_allocation": True,
            "no_backtest": True,
            "no_trade_execution": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def write_asset_registry(payload: Mapping[str, object] | None = None, output_path: str | Path = DEFAULT_REGISTRY_PATH) -> Path:
    path = Path(output_path)
    registry = dict(payload or build_asset_registry())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_asset_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> list[AssetRecord]:
    registry_path = Path(path)
    if not registry_path.exists():
        return list(DEFAULT_ASSETS)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    rows = payload.get("assets") or []
    return [AssetRecord.from_mapping(row) for row in rows if isinstance(row, Mapping)]
