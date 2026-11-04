from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from style_allocation.style_incremental_analysis import (
    _observation_for_date,
    _scored_asset_rows,
    build_style_incremental_analysis,
)


def test_incremental_observation_calculation() -> None:
    score_rows = [
        {"code": "510300.SH", "name": "沪深300ETF", "rank": 1, "score": 80},
        {"code": "159915.SZ", "name": "创业板ETF", "rank": 2, "score": 60},
        {"code": "510500.SH", "name": "中证500ETF", "rank": 3, "score": 55},
        {"code": "510880.SH", "name": "红利ETF", "rank": 4, "score": 45},
    ]
    style_scores = {"growth": 90, "small_cap": 70, "value": 50, "dividend": 40}
    histories = {
        "510300.SH": pd.DataFrame({"trade_date": ["20240101", "20240102"], "close": [100, 101]}),
        "159915.SZ": pd.DataFrame({"trade_date": ["20240101", "20240102"], "close": [100, 110]}),
        "510500.SH": pd.DataFrame({"trade_date": ["20240101", "20240102"], "close": [100, 102]}),
        "510880.SH": pd.DataFrame({"trade_date": ["20240101", "20240102"], "close": [100, 99]}),
    }
    rows = _scored_asset_rows(
        score_rows=score_rows,
        style_scores=style_scores,
        return_histories=histories,
        date_text="20240101",
        horizon=1,
    )
    observation = _observation_for_date(
        mode="unit_test",
        date_text="20240101",
        validation_state="STRUCTURAL_BULL",
        dominant_style="growth",
        rows=rows,
        horizon=1,
        top_n=2,
    )
    assert observation is not None
    assert observation["baseline_return"] == 0.055
    assert observation["style_return"] == 0.06
    assert observation["combined_return"] == 0.055
    assert observation["combined_ic"] is not None
    assert observation["selection_overlap"]["combined_vs_baseline_ratio"] == 1.0


def test_style_incremental_analysis_payload() -> None:
    payload = build_style_incremental_analysis(start_date="20150105", end_date="20260708")
    assert payload["metadata"]["engine"] == "V3.5.7 Style Incremental Information Test"
    assert payload["constraints"]["research_validation_only"] is True
    assert payload["constraints"]["combined_weight_fixed_not_optimized"] is True
    assert payload["constraints"]["style_preference_formula_unchanged"] is True
    assert payload["constraints"]["opportunity_score_formula_unchanged"] is True
    assert payload["constraints"]["no_allocation"] is True
    assert payload["constraints"]["no_etf_weight"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_parameter_optimization"] is True
    assert payload["summary"]["edge_read"]["style_incremental_edge_status"] in {
        "incremental_positive",
        "weak_short_horizon_trace",
        "no_clear_incremental_edge",
    }
    for mode in ("research_proxy", "tradable_etf"):
        assert mode in payload["summary"]
        for horizon in ("20d", "60d"):
            item = payload["summary"][mode][horizon]
            assert item["overall"]["date_count"] > 0
            assert "STRUCTURAL_BULL" in item["by_state"]
            assert "RANGE" in item["by_state"]
            assert "BEAR" in item["by_state"]
            assert "combined_minus_baseline" in item["overall"]["returns"]
            assert "combined_minus_baseline" in item["overall"]["rank_ic"]
    assert payload["sample_observations"]["tradable_etf"]


if __name__ == "__main__":
    test_incremental_observation_calculation()
    test_style_incremental_analysis_payload()
    print("test_style_incremental_analysis ok")
