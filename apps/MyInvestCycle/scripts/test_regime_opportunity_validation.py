from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.regime_conditioned_validation import build_regime_conditioned_validation


def test_regime_conditioned_validation() -> None:
    payload = build_regime_conditioned_validation(start_date="20150105", end_date="20260708", step_sessions=60)
    assert payload["metadata"]["engine"] == "V3.2.3 Regime-Conditioned Opportunity Validation"
    assert payload["metadata"]["score_date_count"] > 0
    assert payload["constraints"]["uses_existing_score"] is True
    assert payload["constraints"]["formula_changed_from_v3_2_1"] is False
    assert payload["constraints"]["state_signal_uses_last_known_signal"] is True
    assert payload["constraints"]["no_allocation"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_parameter_optimization"] is True

    counts = payload["summary"]["score_date_regime_counts"]
    assert counts
    assert "regime_bucket" in payload["tradable_etf_validation"]
    assert "20d" in payload["tradable_etf_validation"]["regime_bucket"]
    assert payload["tradable_etf_validation"]["regime_bucket"]["20d"]
    for section in ("research_proxy_validation", "tradable_etf_validation"):
        assert set(payload[section]) == {"regime_bucket", "structural_state", "macro_state", "market_structure_state", "theme_risk_level"}


if __name__ == "__main__":
    test_regime_conditioned_validation()
    print("test_regime_opportunity_validation ok")
