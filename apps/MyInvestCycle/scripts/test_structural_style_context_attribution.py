from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from style_allocation.structural_style_context_attribution import (
    analyze_context_records,
    build_structural_style_context_attribution,
    context_row_for_date,
    joined_context_records,
)


def test_context_row_for_date_uses_prior_only() -> None:
    rows = [
        {"date": "20240101", "style_context": {"industry_breadth": 0.2}},
        {"date": "20240120", "style_context": {"industry_breadth": 0.6}},
    ]
    assert context_row_for_date(rows, "20240115")["date"] == "20240101"
    assert context_row_for_date(rows, "20240120")["date"] == "20240120"
    assert context_row_for_date(rows, "20231231") is None


def test_joined_context_records_and_hypotheses() -> None:
    observations = [
        {
            "date": "20240120",
            "validation_state": "STRUCTURAL_BULL",
            "dominant_style": "growth",
            "baseline_codes": ["510300.SH"],
            "style_aware_codes": ["159915.SZ"],
            "baseline_return": 0.01,
            "style_aware_return": 0.05,
            "relative_to_baseline": 0.04,
            "style_scores": {"growth": 75, "small_cap": 55, "value": 50, "dividend": 45},
            "style_forward_returns": {"growth": 0.05, "small_cap": 0.01, "value": 0.02, "dividend": 0.0},
        },
        {
            "date": "20240220",
            "validation_state": "STRUCTURAL_BULL",
            "dominant_style": "growth",
            "baseline_codes": ["159915.SZ"],
            "style_aware_codes": ["159915.SZ"],
            "baseline_return": 0.04,
            "style_aware_return": -0.01,
            "relative_to_baseline": -0.05,
            "style_scores": {"growth": 70, "small_cap": 58, "value": 51, "dividend": 45},
            "style_forward_returns": {"growth": -0.01, "small_cap": 0.03, "value": 0.02, "dividend": 0.01},
        },
    ]
    context_rows = [
        {
            "date": "20240120",
            "style_context": {
                "industry_breadth": 0.7,
                "positive_industry_ratio": 0.8,
                "theme_persistence": 75,
                "crowding_score": 35,
                "price_extension": 40,
                "theme_risk_level": "low",
            },
            "data_quality": {"missing_fields": []},
        },
        {
            "date": "20240220",
            "style_context": {
                "industry_breadth": 0.2,
                "positive_industry_ratio": 0.3,
                "theme_persistence": 45,
                "crowding_score": 78,
                "price_extension": 82,
                "theme_risk_level": "high",
            },
            "data_quality": {"missing_fields": []},
        },
    ]
    structural_rows = [
        {"date": "20240120", "features": {"trend": 0.7}},
        {"date": "20240220", "features": {"trend": 0.6}},
    ]
    records = joined_context_records(observations, context_rows, structural_rows)
    assert len(records) == 2
    assert all(record["context_future_safe"] for record in records)
    result = analyze_context_records(records)
    assert result["case_counts"]["success"] == 1
    assert result["context_differences"]["industry_breadth"]["success_minus_failure"] == 0.5
    assert result["hypothesis_tests"][0]["support_score"] >= 1


def test_structural_style_context_attribution_payload() -> None:
    payload = build_structural_style_context_attribution()
    assert payload["metadata"]["engine"] == "V3.5.6 Structural Bull Style Context Re-Attribution"
    assert payload["constraints"]["research_attribution_only"] is True
    assert payload["constraints"]["uses_historical_style_context"] is True
    assert payload["constraints"]["no_etf_allocation"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    for mode in ("research_proxy", "tradable_etf"):
        assert mode in payload["results"]
        for horizon in ("20d", "60d"):
            item = payload["results"][mode][horizon]
            assert "case_counts" in item
            assert "hypothesis_tests" in item
            assert item["constraints"]["context_join_uses_same_day_or_prior_context"] is True


if __name__ == "__main__":
    test_context_row_for_date_uses_prior_only()
    test_joined_context_records_and_hypotheses()
    test_structural_style_context_attribution_payload()
    print("test_structural_style_context_attribution ok")
