from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_validation import build_opportunity_validation


def test_opportunity_validation() -> None:
    payload = build_opportunity_validation(start_date="20150105", end_date="20260708", step_sessions=60)
    assert payload["metadata"]["engine"] == "V3.2.2 Opportunity Score Validation & Factor Attribution"
    assert payload["metadata"]["score_date_count"] > 0
    assert payload["constraints"]["walk_forward"] is True
    assert payload["constraints"]["proxy_return_and_etf_return_separated"] is True
    assert payload["constraints"]["no_allocation"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_parameter_optimization"] is True

    for section in ("research_proxy_validation", "tradable_etf_validation"):
        assert set(payload[section]) == {"5d", "20d", "60d"}
        for horizon, result in payload[section].items():
            assert result["observation_count"] > 0, horizon
            assert "rank_ic" in result
            assert set(result["factor_ic"]) == {"momentum", "relative_strength", "trend_quality", "risk_adjusted", "persistence"}

    assert "no_position_sizing" in payload["constraints"]
    for section in ("research_proxy_validation", "tradable_etf_validation"):
        for result in payload[section].values():
            assert "allocation" not in result
            assert "position" not in result
            assert "trade" not in result


if __name__ == "__main__":
    test_opportunity_validation()
    print("test_opportunity_validation ok")
