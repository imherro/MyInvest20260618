from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.asset_loader import load_asset_history
from asset_opportunity.asset_registry import build_asset_registry
from asset_opportunity.asset_schema import AssetRecord
from scripts.audit_asset_universe import build_asset_universe_audit


def main() -> None:
    registry = build_asset_registry()
    assert registry["constraints"]["etf_only"] is True
    assert registry["constraints"]["no_opportunity_score"] is True
    assert registry["constraints"]["no_backtest"] is True
    assert registry["metadata"]["category_counts"]["industry"] >= 10
    first = AssetRecord.from_mapping(registry["assets"][0])
    history = load_asset_history(first, "20150105", "20260708", cache_only=True)
    assert {"trade_date", "close", "volume"}.issubset(history.columns)
    assert not history.empty
    audit = build_asset_universe_audit(start_date="20150105", end_date="20260708")
    assert audit["constraints"]["no_ranking"] is True
    assert audit["summary"]["enabled_assets"] == registry["metadata"]["asset_count"]
    assert audit["summary"]["category_counts"]["industry"] >= 10
    print("test_asset_opportunity_foundation ok")


if __name__ == "__main__":
    main()
