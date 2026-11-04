from __future__ import annotations

from tests.test_portfolio import _task_data

from tenbagger.monetization import AlphaDecayModel, MonetizationOptimizer, NonlinearPayoffDetector


def test_alpha_decay_model_outputs_curve() -> None:
    factors, prices = _task_data()
    result = AlphaDecayModel().fit(factors, prices)

    assert "curve" in result
    assert "decay_rate" in result


def test_nonlinear_payoff_detector_outputs_sections() -> None:
    factors, prices = _task_data()
    result = NonlinearPayoffDetector().analyze(factors, prices)

    assert "momentum_convexity" in result


def test_monetization_configs_are_available() -> None:
    configs = MonetizationOptimizer(top_k=3)._configs()

    assert any(config["rebalance"] == "weekly" for config in configs)
    assert any(config["weight_mode"] == "score_convex" for config in configs)
