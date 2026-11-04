from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.allocation_policy_engine import build_allocation_policy_snapshot
from allocation_policy.style_constraint_engine import build_style_constraints


def test_style_constraints_respect_weak_incremental_edge() -> None:
    payload = build_style_constraints(
        {
            "macro": {"state": "RECOVERY", "score": 73},
            "structural": {"state": "STRUCTURAL_BULL_ROTATION", "score": 65},
            "market_structure": {"state": "BULL_DIVERGENCE", "breadth": 14.0, "liquidity": 45.0, "index_trend": 78.0},
            "industry_opportunity": {"theme_persistence": 82, "industry_breadth": 0.09, "top_industry_ratio": 0.26},
            "theme_risk": {"level": "medium", "crowding_score": 56, "quality_score": 63, "warnings": ["industry_breadth_narrow"]},
            "style_preference": {
                "dominant_style": "growth",
                "style_environment": {
                    "growth": {"preference_score": 72},
                    "small_cap": {"preference_score": 58},
                    "value": {"preference_score": 55},
                    "dividend": {"preference_score": 60},
                },
            },
            "style_incremental": {"style_incremental_edge_status": "weak_short_horizon_trace"},
        }
    )
    environment = payload["allocation_environment"]
    constraints = payload["risk_constraints"]
    assert environment["growth_allowed"] is True
    assert environment["crowding_control_required"] is True
    assert environment["style_alpha_independent"] is False
    assert constraints["style_score_may_not_expand_budget_by_itself"] is True
    assert constraints["max_single_style_budget"] == "medium_high"
    assert "style_is_descriptor_not_alpha" in payload["style_permissions"]["growth"]["controls"]
    assert payload["constraints"]["no_etf_code"] is True
    assert payload["constraints"]["no_position_sizing"] is True
    assert payload["constraints"]["no_trade_signal"] is True


def test_allocation_policy_snapshot() -> None:
    payload = build_allocation_policy_snapshot()
    assert payload["metadata"]["engine"] == "V4.1 Allocation Policy Foundation"
    assert payload["metadata"]["not_a_portfolio_weight_model"] is True
    assert payload["constraints"]["policy_foundation_only"] is True
    assert payload["constraints"]["qualitative_risk_budget_only"] is True
    assert payload["constraints"]["no_etf_code"] is True
    assert payload["constraints"]["no_asset_weight"] is True
    assert payload["constraints"]["no_portfolio_weight"] is True
    assert payload["constraints"]["no_position_sizing"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_order_generation"] is True
    assert payload["constraints"]["router_unchanged"] is True
    assert payload["constraints"]["alpha_model_unchanged"] is True

    policy = payload["policy"]
    assert policy["policy_state"]
    assert policy["allocation_environment"]["style_incremental_edge_status"]
    assert policy["risk_constraints"]["style_score_may_not_expand_budget_by_itself"] is True
    assert set(policy["style_permissions"]) == {"growth", "small_cap", "value", "dividend"}
    for row in policy["style_permissions"].values():
        assert "budget_ceiling" in row
        assert "target_weight" not in row
        assert "etf" not in row


if __name__ == "__main__":
    test_style_constraints_respect_weak_incremental_edge()
    test_allocation_policy_snapshot()
    print("test_allocation_policy ok")
