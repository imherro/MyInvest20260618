from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.protection_score_validation import (
    build_protection_score_validation,
    write_protection_score_validation,
)


def main() -> None:
    payload = build_protection_score_validation()
    summary = payload["summary"]
    model_comparison = payload["model_comparison"]
    phase_consistency = payload["phase_consistency"]
    threshold = payload["threshold_audit"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert payload["metadata"]["engine"] == "V6.4 Protection Score Robustness & Conditional Validation"
    assert summary["joined_sample_count"] == 115
    assert summary["ready_for_mapper_change"] is False
    assert summary["ready_for_exposure_change"] is False
    assert summary["conclusion"] in {
        "protection_score_edge_not_confirmed",
        "protection_score_research_value_confirmed_not_policy_ready",
        "protection_score_signal_visible_but_not_robust",
    }

    for model_id in (
        "model_a_risk_gradient_bucket",
        "model_b_protection_score_bucket",
        "model_c_risk_gradient_plus_protection_score",
    ):
        model = model_comparison[model_id]
        assert model["high_group_sample_count"] >= 0
        assert 0 <= model["high_risk_event_capture_rate"] <= 1
        assert 0 <= model["false_warning_rate"] <= 1

    assert len(payload["phase_analysis"]) == 4
    assert phase_consistency["model_b_protection_score"]["phase_consistency"] in {
        "insufficient_evidence",
        "weak",
        "medium",
        "high",
    }
    assert threshold["fixed_thresholds_reused_from_v5_11"] is True
    assert threshold["thresholds_were_not_optimized"] is True
    assert time_safety["feature_release_or_source_lte_signal_date"] is True
    assert time_safety["violation_count"] == 0
    assert data_quality["uses_fixed_v6_3_protection_score"] is True
    assert data_quality["uses_fixed_v5_10_risk_gradient"] is True
    assert data_quality["uses_fixed_v5_11_thresholds"] is True
    assert data_quality["no_parameter_optimization"] is True
    assert constraints["does_not_modify_protection_weight"] is True
    assert constraints["does_not_modify_bucket_threshold"] is True
    assert constraints["does_not_modify_mapper"] is True
    assert constraints["does_not_modify_exposure_level"] is True
    assert constraints["does_not_generate_position"] is True
    assert constraints["no_trade_signal"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_protection_score_validation(payload, Path(tmpdir) / "protection_score_validation.json")
        assert output.exists()

    print("test_protection_score_validation ok")


if __name__ == "__main__":
    main()
