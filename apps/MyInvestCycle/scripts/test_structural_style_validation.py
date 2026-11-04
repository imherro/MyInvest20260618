from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.structural_style_rotation_validation import build_structural_style_validation
from style_allocation.structural_style_validation import style_drift_analysis, structural_bull_rows


def test_structural_helpers() -> None:
    rows = [
        {"date": "20240101", "validation_state": "STRUCTURAL_BULL", "dominant_style": "growth"},
        {"date": "20240122", "validation_state": "RANGE", "dominant_style": "value"},
        {"date": "20240201", "validation_state": "STRUCTURAL_BULL", "dominant_style": "value"},
    ]
    filtered = structural_bull_rows(rows)
    assert len(filtered) == 2
    drift = style_drift_analysis(filtered)
    assert drift["date_count"] == 2
    assert drift["transition_count"] == 1
    assert drift["structural_bull_style_transition"][0]["from"] == "growth"
    assert drift["structural_bull_style_transition"][0]["to"] == "value"


def test_structural_style_validation() -> None:
    payload = build_structural_style_validation(start_date="20150105", end_date="20260708")
    assert payload["metadata"]["engine"] == "V3.5.3 Structural Bull Style Rotation Validation"
    assert payload["metadata"]["validation_scope"] == "STRUCTURAL_BULL_ONLY"
    assert payload["constraints"]["research_validation_only"] is True
    assert payload["constraints"]["structural_bull_only"] is True
    assert payload["constraints"]["style_preference_formula_unchanged_from_v3_5_2"] is True
    assert payload["constraints"]["no_future_function_in_signal"] is True
    assert payload["constraints"]["no_etf_allocation"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["summary"]["edge_status"] in {
        "structural_bull_confirmed",
        "positive_spread_not_robust",
        "short_horizon_only",
        "weak_or_negative",
        "inconclusive",
    }
    for mode in ("research_proxy", "tradable_etf"):
        assert mode in payload["results"]
        for horizon in ("20d", "60d"):
            item = payload["results"][mode][horizon]
            assert "summary" in item
            assert "style_drift" in item
            assert item["summary"]["date_count"] >= 0
            assert "baseline" in item["summary"]
            assert "style_aware" in item["summary"]


if __name__ == "__main__":
    test_structural_helpers()
    test_structural_style_validation()
    print("test_structural_style_validation ok")
