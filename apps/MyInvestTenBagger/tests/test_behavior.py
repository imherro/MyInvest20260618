from __future__ import annotations

from tests.test_regime import _index_data

from tenbagger.behavior import BehaviorFlowEngine, BehaviorValidator
from tenbagger.regime import MarketRegimeEngine


def test_behavior_flow_engine_outputs_required_indexes() -> None:
    regime = MarketRegimeEngine().run(_index_data()).daily
    result = BehaviorFlowEngine().run(regime)
    latest = result.latest

    assert 0 <= latest["retail_pressure_index"] <= 1
    assert 0 <= latest["institutional_flow_index"] <= 1
    assert 0 <= latest["panic_index"] <= 1
    assert 0 <= latest["fomo_index"] <= 1
    assert latest["crowding_level"] in {"low", "medium", "high", "extreme"}
    assert latest["flow_price_divergence"] in {
        "neutral",
        "buying_without_price_response",
        "price_up_flow_down",
        "aligned_accumulation",
        "aligned_distribution",
    }


def test_behavior_validator_rejects_future_labels_and_factor_alpha() -> None:
    regime = MarketRegimeEngine().run(_index_data()).daily
    daily = BehaviorFlowEngine().run(regime).daily
    validation = BehaviorValidator().validate(daily)

    assert validation["uses_future_return_labels"] is False
    assert validation["uses_factor_alpha"] is False
    assert validation["walk_forward_features_only"] is True
    assert validation["all_scores_bounded_0_1"] is True
