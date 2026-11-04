from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_policy_validation import (
    build_exposure_policy_validation,
    write_exposure_policy_validation,
)


def main() -> None:
    payload = build_exposure_policy_validation()
    summary = payload["summary"]
    models = payload["model_comparison"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert payload["metadata"]["engine"] == "V6.1 Adaptive Exposure Policy Simulation Validation"
    assert summary["joined_sample_count"] == 115
    assert summary["model_count"] == 3
    assert summary["primary_candidate_count"] == 2
    assert summary["model_b_c_flag_sets_identical"] is True
    assert summary["policy_validation_status"] == "diagnostic_not_ready_for_policy_change"
    assert summary["ready_for_mapper_change"] is False
    assert summary["ready_for_exposure_change"] is False

    model_a = models["model_a_baseline_v5_1"]
    model_b = models["model_b_v5_1_plus_risk_gradient_flag"]
    model_c = models["model_c_v5_1_plus_primary_candidate_context"]
    assert model_a["diagnostic_flag_count"] == 0
    assert model_b["diagnostic_flag_count"] == 14
    assert model_c["diagnostic_flag_count"] == 14
    assert model_b["high_risk_event_capture_rate"] < 0.5
    assert model_b["false_warning_rate"] > 0.5
    assert model_b["status"] == "diagnostic_weak"
    assert model_c["status"] == "diagnostic_weak"

    assert time_safety["feature_release_or_source_lte_signal_date"] is True
    assert time_safety["violation_count"] == 0
    assert data_quality["uses_fixed_v5_1_exposure_simulation"] is True
    assert data_quality["uses_v5_13_primary_candidates_only"] is True
    assert data_quality["exposure_level_unchanged"] is True
    assert data_quality["mapper_unchanged"] is True
    assert constraints["does_not_modify_mapper"] is True
    assert constraints["does_not_modify_exposure_level"] is True
    assert constraints["does_not_generate_position"] is True
    assert constraints["no_etf_code"] is True
    assert constraints["no_trade_signal"] is True
    assert constraints["no_best_rule_selection"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_exposure_policy_validation(payload, Path(tmpdir) / "exposure_policy_validation.json")
        assert output.exists()

    print("test_exposure_policy_validation ok")


if __name__ == "__main__":
    main()
