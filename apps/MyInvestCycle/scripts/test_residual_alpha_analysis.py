from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.factor_neutral_attribution import build_residual_alpha_analysis


def test_residual_alpha_analysis() -> None:
    payload = build_residual_alpha_analysis(start_date="20150105", end_date="20260708")
    assert payload["metadata"]["engine"] == "V3.4.5 Residual Alpha Attribution & Factor Neutralization Analysis"
    assert payload["constraints"]["analysis_only"] is True
    assert payload["constraints"]["ordinary_linear_regression_only"] is True
    assert payload["constraints"]["model_unchanged"] is True
    assert payload["constraints"]["router_unchanged"] is True
    assert payload["constraints"]["no_trade_signal"] is True

    assert len(payload["factor_universe"]) >= 6
    assert {period["label"] for period in payload["periods"]} == {"2020-2021", "2022", "2023", "2024-2026"}
    for period in payload["periods"]:
        model = period["factor_model"]
        assert model["observations"] > 0
        assert "factor_neutral_residual_metrics" in period
        if model.get("available"):
            assert "betas" in model
            assert "r_squared" in model
            assert "linear_return_sum" in model
            assert period["factor_neutral_residual_metrics"]


if __name__ == "__main__":
    test_residual_alpha_analysis()
    print("test_residual_alpha_analysis ok")
