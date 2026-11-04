from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_allocation.structural_bull_policy import refine_structural_bull_policy


def _structural(industry_breadth: float = 0.55) -> dict[str, object]:
    return {
        "structural_state": "STRUCTURAL_BULL_ROTATION",
        "evidence": {
            "market_structure": {"state": "BULL_DIVERGENCE"},
            "industry_opportunity": {
                "industry_strength": 70,
                "theme_persistence": 82,
                "rotation_health": 58,
                "metrics": {"industry_breadth": industry_breadth, "top_industry_ratio": 0.18},
            },
        },
    }


def test_low_risk_structural_bull_is_healthy() -> None:
    policy = refine_structural_bull_policy(
        _structural(),
        {"theme_risk_level": "low", "quality_score": 75, "crowding_score": 30},
    )
    assert policy["allocation_structural_state"] == "STRUCTURAL_BULL_HEALTHY"
    assert policy["risk_budget"] == "high"
    assert policy["constraints"]["allocation_policy_only"] is True


def test_high_risk_structural_bull_is_overheated() -> None:
    policy = refine_structural_bull_policy(
        _structural(),
        {"theme_risk_level": "high", "quality_score": 42, "crowding_score": 76},
    )
    assert policy["allocation_structural_state"] == "STRUCTURAL_BULL_OVERHEATED"
    assert policy["risk_budget"] == "medium"


def test_non_structural_bull_does_not_apply() -> None:
    policy = refine_structural_bull_policy(
        {"structural_state": "WEAK_MARKET", "evidence": {}},
        {"theme_risk_level": "low", "quality_score": 75, "crowding_score": 30},
    )
    assert policy["applies"] is False
    assert policy["risk_budget"] is None


if __name__ == "__main__":
    test_low_risk_structural_bull_is_healthy()
    test_high_risk_structural_bull_is_overheated()
    test_non_structural_bull_does_not_apply()
    print("ok")
