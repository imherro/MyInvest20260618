from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.two_axis_context_validation import (
    build_two_axis_context_validation,
    write_two_axis_context_validation,
)


def main() -> None:
    payload = build_two_axis_context_validation()
    summary = payload["summary"]
    two_axis = payload["dimension_metrics"]["two_axis"]
    comparison = payload["dimension_comparison"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert payload["metadata"]["engine"] == "V6.5 Adaptive Context Two-Axis Validation"
    assert summary["joined_sample_count"] == 115
    assert summary["ready_for_mapper_change"] is False
    assert summary["ready_for_exposure_change"] is False
    assert summary["conclusion"] in {
        "risk_axis_visible_opportunity_axis_weak",
        "two_axis_research_value_visible_not_policy_ready",
        "two_axis_context_not_validated",
    }

    for label in ("PARTICIPATE", "PROTECT_BUT_PARTICIPATE", "WAIT", "AVOID"):
        assert label in two_axis
        assert two_axis[label]["sample_count"] >= 0
        assert 0 <= two_axis[label]["future_high_risk_rate"] <= 1
        assert 0 <= two_axis[label]["future_opportunity_rate"] <= 1

    assert comparison["two_axis_risk_spread_rank"] in {"leading", "not_leading"}
    assert comparison["two_axis_opportunity_spread_rank"] in {"leading", "not_leading"}
    assert time_safety["feature_release_or_source_lte_signal_date"] is True
    assert time_safety["violation_count"] == 0
    assert data_quality["uses_fixed_v6_3_participation_score"] is True
    assert data_quality["uses_fixed_v6_3_protection_score"] is True
    assert data_quality["two_axis_thresholds_reuse_v6_3_buckets"] is True
    assert data_quality["no_parameter_optimization"] is True
    assert constraints["research_label_only"] is True
    assert constraints["does_not_modify_bucket_threshold"] is True
    assert constraints["does_not_modify_mapper"] is True
    assert constraints["does_not_modify_exposure_level"] is True
    assert constraints["does_not_generate_position"] is True
    assert constraints["no_trade_signal"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_two_axis_context_validation(payload, Path(tmpdir) / "two_axis_context_validation.json")
        assert output.exists()

    print("test_two_axis_context_validation ok")


if __name__ == "__main__":
    main()
