from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.alpha_regime_router import build_alpha_regime_decision
from asset_opportunity.regime_alpha_schema import AlphaRegimeDecision


def test_alpha_regime_router() -> None:
    broad = build_alpha_regime_decision("20150106")
    assert broad["alpha_regime"] == "BROAD_BULL"
    assert broad["recommended_model"] == "trend_following"
    assert broad["state_signal_date"] <= broad["date"]

    range_decision = build_alpha_regime_decision("20200218")
    assert range_decision["alpha_regime"] in {"RANGE", "BEAR", "BROAD_BULL", "STRUCTURAL_BULL", "HIGH_CROWDING"}
    assert range_decision["state_signal_date"] <= range_decision["date"]

    latest = build_alpha_regime_decision("20260708")
    assert latest["recommended_model"] in {"trend_following", "rotation_alpha", "mean_reversion", "defensive_quality"}
    assert latest["constraints"]["does_not_change_opportunity_score"] is True
    assert latest["constraints"]["no_allocation"] is True
    assert latest["constraints"]["no_trade_signal"] is True
    assert latest["constraints"]["no_backtest"] is True
    AlphaRegimeDecision.from_mapping(latest)


if __name__ == "__main__":
    test_alpha_regime_router()
    print("test_alpha_regime_router ok")
