from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.alpha_portfolio_risk_validation import build_alpha_portfolio_risk_validation


def test_alpha_portfolio_risk_control() -> None:
    payload = build_alpha_portfolio_risk_validation(start_date="20150105", end_date="20260708")
    assert payload["metadata"]["engine"] == "V3.4.3 Alpha Portfolio Risk Control Layer"
    assert payload["constraints"]["simulation_only"] is True
    assert payload["constraints"]["model_formulas_frozen"] is True
    assert payload["constraints"]["theme_concentration_monitor_only"] is True
    assert payload["constraints"]["no_parameter_optimization"] is True
    assert payload["constraints"]["no_best_parameter_selection"] is True
    assert payload["constraints"]["no_trade_signal"] is True

    scenarios = payload["scenarios"]
    assert len(scenarios) == 10
    assert "step20_cost10bp_min20" in scenarios
    assert "step20_cost10bp_min0" in scenarios

    primary = scenarios["step20_cost10bp_min20"]["strategies"]["tradable_etf"]["router_selected_model_top3"]
    metrics = primary["metrics"]
    assert metrics["rebalance_count"] > 0
    assert "cagr" in metrics
    assert "calmar" in metrics
    assert "total_turnover" in metrics
    assert primary["theme_concentration"]["monitor_only"] is True
    assert primary["theme_concentration"]["average_concentration_level"] in {"unknown", "diversified", "elevated", "high"}

    summary = payload["summary"]
    assert len(summary["rebalance_sensitivity"]) == 3
    assert len(summary["cost_sensitivity"]) == 3
    assert len(summary["minimum_holding_sensitivity"]) == 2


if __name__ == "__main__":
    test_alpha_portfolio_risk_control()
    print("test_alpha_portfolio_risk_control ok")
