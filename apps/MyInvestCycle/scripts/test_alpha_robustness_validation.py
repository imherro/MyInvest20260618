from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.rolling_validation import build_alpha_robustness_validation


def test_alpha_robustness_validation() -> None:
    payload = build_alpha_robustness_validation(start_date="20150105", end_date="20260708")
    assert payload["metadata"]["engine"] == "V3.4.4 Alpha Portfolio Robustness & Style Attribution Validation"
    assert payload["metadata"]["rebalance_step"] == 60
    assert payload["metadata"]["transaction_cost"] == 0.001
    assert payload["constraints"]["analysis_only"] is True
    assert payload["constraints"]["model_unchanged"] is True
    assert payload["constraints"]["router_unchanged"] is True
    assert payload["constraints"]["step60_not_promoted_to_default"] is True
    assert payload["constraints"]["no_theme_cap"] is True
    assert payload["constraints"]["no_trade_signal"] is True

    periods = payload["periods"]
    assert {period["label"] for period in periods} == {"2020-2021", "2022", "2023", "2024-2026"}
    for period in periods:
        assert "portfolio" in period
        assert "spreads" in period
        assert "style_exposure" in period
        assert "vs_510500.SH" in period["spreads"]

    exposure = payload["style_exposure"]
    assert exposure["constraints"]["analysis_only"] is True
    assert exposure["latest_exposure"]
    assert payload["summary"]["interpretation"]


if __name__ == "__main__":
    test_alpha_robustness_validation()
    print("test_alpha_robustness_validation ok")
