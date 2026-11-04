from __future__ import annotations

from tests.test_portfolio import _task_data

from tenbagger.optimization import FactorNeutralizer, FactorWeightOptimizer, RegimeDetector


def test_factor_neutralizer_adds_neutral_columns() -> None:
    factors, prices = _task_data()
    neutralized = FactorNeutralizer().neutralize(factors, prices)

    assert "growth_score_neutral" in neutralized.columns
    assert neutralized["growth_score_neutral"].between(0, 100).all()


def test_regime_detector_outputs_regime_columns() -> None:
    factors, prices = _task_data()
    regimes = RegimeDetector().detect(prices, factors)

    assert {"date", "market_regime", "style_regime"}.issubset(regimes.columns)
    assert not regimes.empty


def test_weight_grid_has_candidates() -> None:
    optimizer = FactorWeightOptimizer(step=0.5, top_k=3)

    assert optimizer._weight_grid()
