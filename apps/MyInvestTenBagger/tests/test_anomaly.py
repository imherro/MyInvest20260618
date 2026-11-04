from __future__ import annotations

from tests.test_structure import _behavior_daily, _prices

from tenbagger.anomaly import AnomalyValidator, StructuralAnomalyEngine
from tenbagger.structure import MarketStructureEngine


def _structure_daily():
    prices = _prices()
    return MarketStructureEngine().run(prices, _behavior_daily(prices)).daily


def test_anomaly_engine_outputs_required_scores() -> None:
    result = StructuralAnomalyEngine().run(_structure_daily())
    latest = result.latest

    for key in [
        "structural_break_prob",
        "correlation_break_prob",
        "flow_shock_prob",
        "behavioral_anomaly_score",
        "anomaly_score",
    ]:
        assert 0 <= latest[key] <= 1
    assert latest["systemic_risk_level"] in {"low", "medium", "high"}


def test_anomaly_validator_keeps_detection_contract() -> None:
    daily = StructuralAnomalyEngine().run(_structure_daily()).daily
    validation = AnomalyValidator().validate(daily)

    assert validation["uses_future_return_labels"] is False
    assert validation["uses_alpha_model"] is False
    assert validation["predicts_market_direction"] is False
    assert validation["anomaly_is_structure_deviation"] is True
    assert validation["all_scores_bounded_0_1"] is True
