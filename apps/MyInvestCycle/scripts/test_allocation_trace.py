from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_allocation.decision_trace import build_allocation_trace_snapshot


def allocation_payload() -> dict[str, object]:
    return {
        "engine": "test allocation",
        "as_of": "20260707",
        "structural_state": "STRUCTURAL_BULL_ROTATION",
        "allocation_intent": {
            "risk_budget": "medium",
            "equity_exposure_range": "50-70%",
            "style_preference": ["industry_rotation", "quality_filter"],
        },
        "evidence": {
            "macro": {"state": "RECOVERY", "score": 73},
            "market_structure": {"state": "BULL_DIVERGENCE", "breadth": 14},
            "industry_opportunity": {"industry_strength": 55, "theme_persistence": 82},
            "theme_risk": {"risk_level": "medium", "quality_score": 63, "crowding_score": 56},
        },
        "constraints": {
            "no_etf_code": True,
            "no_buy_sell": True,
            "no_order": True,
            "no_broker_connection": True,
        },
        "data_quality": {"no_future_data": True},
    }


def test_trace_explains_adjustment() -> None:
    snapshot = build_allocation_trace_snapshot("20260708", allocation_payload=allocation_payload())
    trace = snapshot["decision_trace"]
    assert trace["adjustment_path"][0]["value"] == "medium_high"
    assert trace["adjustment_path"][1]["result"] == "medium"
    assert "index_trend_strong_but_breadth_weak" in trace["conflicts"]


def test_trace_keeps_intent_unchanged() -> None:
    snapshot = build_allocation_trace_snapshot("20260708", allocation_payload=allocation_payload())
    assert snapshot["allocation_intent"]["risk_budget"] == "medium"
    assert snapshot["audit"]["passed"] is True
    assert snapshot["constraints"]["does_not_change_allocation_intent"] is True


def main() -> None:
    test_trace_explains_adjustment()
    test_trace_keeps_intent_unchanged()


if __name__ == "__main__":
    main()
