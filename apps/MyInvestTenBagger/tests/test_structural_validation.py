from __future__ import annotations

from tests.test_portfolio import _task_data

from tenbagger.alpha_validation import AlphaValidator
from tenbagger.structural_validation import RandomizationTest, StructuralAlphaValidator


def test_structural_validator_outputs_alpha_classification() -> None:
    factors, prices = _task_data()
    result = StructuralAlphaValidator(top_k=3, random_iterations=5).run(factors, prices)

    assert result.classification in {"REAL", "PSEUDO", "NO ALPHA"}
    assert "rank_ic_gt_0_05" in result.criteria
    assert "primary_failure" in result.failure_mode_diagnosis


def test_randomization_test_outputs_p_values() -> None:
    factors, prices = _task_data()
    scored = StructuralAlphaValidator(top_k=3, random_iterations=5)._score_inputs(factors, prices)
    enriched = AlphaValidator(horizons=(21,)).attach_forward_returns(scored, prices)
    result = RandomizationTest(iterations=5, random_seed=7).run(enriched)

    assert "label_shuffle" in result
    assert "p_value" in result["feature_permutation"]
