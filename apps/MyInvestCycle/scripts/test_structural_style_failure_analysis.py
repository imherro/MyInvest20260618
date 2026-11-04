from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from style_allocation.structural_style_failure_analysis import (
    analyze_structural_style_failures,
    build_structural_style_failure_analysis,
    structural_style_case_records,
)


def test_case_record_join_and_split() -> None:
    rows = [
        {
            "date": "20240101",
            "validation_state": "STRUCTURAL_BULL",
            "dominant_style": "growth",
            "baseline_codes": ["510300.SH", "510500.SH"],
            "style_aware_codes": ["159915.SZ", "588000.SH"],
            "baseline_return": 0.01,
            "style_aware_return": 0.03,
            "relative_to_baseline": 0.02,
            "style_ic": 0.4,
            "style_scores": {"growth": 70, "small_cap": 55, "value": 52, "dividend": 40},
            "style_forward_returns": {"growth": 0.03, "small_cap": 0.01, "value": 0.02, "dividend": -0.01},
        },
        {
            "date": "20240201",
            "validation_state": "STRUCTURAL_BULL",
            "dominant_style": "growth",
            "baseline_codes": ["510300.SH", "510500.SH"],
            "style_aware_codes": ["159915.SZ", "588000.SH"],
            "baseline_return": 0.03,
            "style_aware_return": -0.01,
            "relative_to_baseline": -0.04,
            "style_ic": -0.4,
            "style_scores": {"growth": 75, "small_cap": 54, "value": 50, "dividend": 42},
            "style_forward_returns": {"growth": -0.01, "small_cap": 0.04, "value": 0.02, "dividend": 0.01},
        },
        {"date": "20240301", "validation_state": "RANGE", "relative_to_baseline": 1},
    ]
    structural_rows = [
        {"date": "20240101", "features": {"trend": 0.7, "breadth": 0.6, "liquidity": 0.5}},
        {"date": "20240201", "features": {"trend": 0.5, "breadth": 0.4, "liquidity": 0.3}},
    ]
    records = structural_style_case_records(rows, structural_rows)
    assert len(records) == 2
    assert records[0]["case_type"] == "success"
    assert records[1]["case_type"] == "failure"
    analysis = analyze_structural_style_failures(rows, structural_rows)
    assert analysis["case_counts"]["success"] == 1
    assert analysis["case_counts"]["failure"] == 1
    assert analysis["success"]["feature_means"]["trend"] == 0.7
    assert analysis["failure"]["feature_means"]["liquidity"] == 0.3
    assert analysis["condition_candidates"]["success_associations"]
    assert analysis["case_examples"]["largest_failure_spreads"][0]["date"] == "20240201"


def test_structural_style_failure_analysis_payload() -> None:
    payload = build_structural_style_failure_analysis(start_date="20150105", end_date="20260708")
    assert payload["metadata"]["engine"] == "V3.5.4 Structural Bull Style Failure Attribution"
    assert payload["metadata"]["validation_scope"] == "STRUCTURAL_BULL_SUCCESS_FAILURE_ATTRIBUTION"
    assert payload["constraints"]["research_attribution_only"] is True
    assert payload["constraints"]["style_preference_formula_unchanged"] is True
    assert payload["constraints"]["no_etf_allocation"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["field_coverage"]["requested_but_unavailable_historical_fields"]
    for mode in ("research_proxy", "tradable_etf"):
        assert mode in payload["results"]
        for horizon in ("20d", "60d"):
            result = payload["results"][mode][horizon]
            assert "case_counts" in result
            assert result["case_counts"]["total"] >= 0
            assert "feature_differences" in result
            assert "condition_candidates" in result


if __name__ == "__main__":
    test_case_record_join_and_split()
    test_structural_style_failure_analysis_payload()
    print("test_structural_style_failure_analysis ok")
