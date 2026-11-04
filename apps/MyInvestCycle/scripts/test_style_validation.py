from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.style_attribution_validation import build_style_validation
from style_allocation.style_schema import STYLE_IDS
from style_allocation.style_validation import build_historical_style_preference, classify_validation_state


def test_style_preference_formula() -> None:
    row = {
        "date": "20240101",
        "structural_regime": "bull",
        "regime": "bull",
        "features": {"trend": 0.8, "breadth": 0.7, "liquidity": 0.6, "volatility": 0.7},
    }
    scores = [
        {"code": "159915.SZ", "name": "创业板ETF", "rank": 1, "score": 70},
        {"code": "510500.SH", "name": "中证500ETF", "rank": 2, "score": 60},
        {"code": "510300.SH", "name": "沪深300ETF", "rank": 3, "score": 55},
        {"code": "510880.SH", "name": "红利ETF", "rank": 4, "score": 45},
    ]
    preference = build_historical_style_preference(date_text="20240101", structural_row=row, score_rows=scores)
    assert classify_validation_state(row) == "BROAD_BULL"
    assert preference["dominant_style"] in STYLE_IDS
    assert set(preference["style_scores"]) == set(STYLE_IDS)
    assert abs(sum(preference["relative_signal_share"].values()) - 1.0) <= 0.00001


def test_style_validation() -> None:
    payload = build_style_validation(start_date="20150105", end_date="20260708")
    assert payload["metadata"]["engine"] == "V3.5.2 Style Preference Validation & Attribution Engine"
    assert payload["metadata"]["top_n"] == 3
    assert payload["constraints"]["research_validation_only"] is True
    assert payload["constraints"]["style_preference_frozen"] is True
    assert payload["constraints"]["no_future_function_in_signal"] is True
    assert payload["constraints"]["no_etf_weight"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_parameter_optimization"] is True
    assert set(payload["style_universe"]) == set(STYLE_IDS)
    assert payload["summary"]["score_start"]
    assert payload["summary"]["score_end"]
    assert payload["summary"]["edge_read"]["style_preference_edge_status"] in {
        "positive",
        "short_horizon_only",
        "weak_or_inconclusive",
    }
    for mode in ("research_proxy", "tradable_etf"):
        assert mode in payload["summary"]
        for horizon in ("20d", "60d"):
            assert horizon in payload["summary"][mode]
            overall = payload["summary"][mode][horizon]["overall"]
            assert overall["date_count"] > 0
            assert "style_ic" in overall
            assert "spread" in overall
            assert "hit_rate" in overall
            assert "by_state" in payload["summary"][mode][horizon]
    assert payload["sample_preferences"]


if __name__ == "__main__":
    test_style_preference_formula()
    test_style_validation()
    print("test_style_validation ok")
