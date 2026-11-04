from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_score_engine import build_asset_opportunity_snapshot


def test_asset_opportunity_snapshot() -> None:
    payload = build_asset_opportunity_snapshot("20260708", start_date="20150105", cache_only=True)
    assert payload["metadata"]["engine"] == "V3.2.1 Asset Opportunity Score Engine"
    assert payload["metadata"]["asset_count"] == 17
    assert payload["metadata"]["as_of"] <= payload["metadata"]["requested_as_of"]
    assert payload["constraints"]["no_allocation"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_backtest"] is True
    assert payload["data_quality"]["no_future_data"] is True
    assert payload["data_quality"]["theme_risk_status"]["no_future_data"] is True
    assert payload["summary"]["theme_risk_as_of"] <= payload["metadata"]["as_of"]

    rows = payload["assets"]
    assert len(rows) == 17
    assert [row["rank"] for row in rows] == list(range(1, 18))
    assert rows == sorted(rows, key=lambda row: (float(row["score"]), str(row["code"])), reverse=True)
    for row in rows:
        assert 0.0 <= float(row["score"]) <= 100.0
        assert set(row["components"]) == {"momentum", "relative_strength", "trend_quality", "risk_adjusted", "persistence"}
        assert set(row["penalty"]) == {"extension", "crowding"}
        assert "weight" not in row
        assert "allocation" not in row
        assert "trade" not in row
        assert row["metrics"]["as_of"] <= payload["metadata"]["as_of"]

    semi = next(row for row in rows if row["code"] == "512480.SH")
    assert semi["mapping_method"] == "research_only"
    assert semi["research_source"]["code"] == "801080.SI"
    assert semi["research_source"]["research_only"] is True

    large = next(row for row in rows if row["code"] == "510300.SH")
    assert large["mapping_method"] == "direct_etf_history_only"
    assert large["research_source"]["code"] == "510300.SH"
    assert large["research_source"]["research_only"] is False


if __name__ == "__main__":
    test_asset_opportunity_snapshot()
    print("test_asset_opportunity_score ok")
