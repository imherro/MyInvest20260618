from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.alpha_portfolio_simulator import build_alpha_portfolio_simulation


def test_alpha_portfolio_simulation() -> None:
    payload = build_alpha_portfolio_simulation(start_date="20150105", end_date="20260708", step_sessions=60)
    assert payload["metadata"]["engine"] == "V3.4.1 Alpha Model Portfolio Simulation Foundation"
    assert payload["metadata"]["score_date_count"] > 0
    assert payload["metadata"]["top_n_values"] == [3, 5]
    assert payload["constraints"]["simulation_only"] is True
    assert payload["constraints"]["top_n_fixed"] is True
    assert payload["constraints"]["t_plus_1_entry"] is True
    assert payload["constraints"]["no_parameter_optimization"] is True
    assert payload["constraints"]["no_position_sizing"] is True
    assert payload["constraints"]["no_trade_signal"] is True

    for section in ("research_proxy_simulation", "tradable_etf_simulation"):
        assert "opportunity_score" in payload[section]
        assert "router_selected_model" in payload[section]
        for model in ("opportunity_score", "router_selected_model"):
            assert set(payload[section][model]) == {"top3", "top5"}
            assert set(payload[section][model]["top3"]) == {"5d", "20d", "60d"}
            assert payload[section][model]["top3"]["20d"]["observation_count"] > 0


if __name__ == "__main__":
    test_alpha_portfolio_simulation()
    print("test_alpha_portfolio_simulation ok")
