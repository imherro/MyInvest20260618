from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import build_asset_proxy_registry, read_asset_proxy_registry
from scripts.audit_asset_proxy_coverage import build_asset_proxy_coverage_audit


def main() -> None:
    registry = build_asset_proxy_registry()
    assert registry["constraints"]["research_proxy_only"] is True
    assert registry["constraints"]["no_opportunity_score"] is True
    assert registry["metadata"]["with_proxy"] == 10
    mappings = read_asset_proxy_registry()
    proxy_mappings = [mapping for mapping in mappings if mapping.research_proxy is not None]
    assert len(proxy_mappings) == 10
    history = load_research_proxy_history(proxy_mappings[0], "20150105", "20260708", cache_only=True)
    assert not history.empty
    assert {"trade_date", "close", "volume"}.issubset(history.columns)
    audit = build_asset_proxy_coverage_audit(start_date="20150105", end_date="20260708")
    assert audit["summary"]["with_proxy"] == 10
    assert audit["summary"]["missing_proxy"] == []
    assert audit["summary"]["research_coverage_start"] <= "20150105"
    assert audit["constraints"]["does_not_fabricate_etf_history"] is True
    print("test_asset_proxy_layer ok")


if __name__ == "__main__":
    main()
