from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.alpha_portfolio_backtest import build_alpha_portfolio_backtest


def test_alpha_portfolio_backtest() -> None:
    payload = build_alpha_portfolio_backtest(start_date="20150105", end_date="20260708", step_sessions=60)
    assert payload["metadata"]["engine"] == "V3.4.2 Alpha Portfolio Simulation & Risk Validation"
    assert payload["metadata"]["transaction_cost"] == 0.001
    assert payload["constraints"]["simulation_only"] is True
    assert payload["constraints"]["equal_weight"] is True
    assert payload["constraints"]["t_plus_1_entry"] is True
    assert payload["constraints"]["transaction_cost_explicit"] is True
    assert payload["constraints"]["no_dynamic_weight_optimization"] is True
    assert payload["constraints"]["no_parameter_search"] is True
    assert payload["constraints"]["no_trade_signal"] is True

    for mode in ("research_proxy", "tradable_etf"):
        assert "router_selected_model_top3" in payload["strategies"][mode]
        result = payload["strategies"][mode]["router_selected_model_top3"]
        assert result["metrics"]["rebalance_count"] > 0
        assert result["equity_curve"]
        assert "theme_concentration" in result
    assert set(payload["benchmarks"]) == {"510300.SH", "510500.SH"}


if __name__ == "__main__":
    test_alpha_portfolio_backtest()
    print("test_alpha_portfolio_backtest ok")
