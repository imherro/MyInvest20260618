from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.context_information_attribution import (
    build_context_information_attribution,
    write_context_information_attribution,
)


def main() -> None:
    payload = build_context_information_attribution()
    summary = payload["summary"]
    layers = payload["layer_attribution"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert payload["metadata"]["engine"] == "V6.6 Adaptive Context Information Attribution Audit"
    assert summary["joined_sample_count"] == 115
    assert summary["layer_count"] == 4
    assert summary["ready_for_mapper_change"] is False
    assert summary["ready_for_exposure_change"] is False
    assert summary["conclusion"] == "risk_layers_have_research_value_opportunity_layer_not_ready"

    expected = {
        "layer_0_v5_1_exposure_level",
        "layer_1_risk_gradient",
        "layer_2_protection_score",
        "layer_3_two_axis_context",
    }
    assert {layer["layer_id"] for layer in layers} == expected
    for layer in layers:
        assert layer["sample_count"] == 115
        assert 0 <= layer["coverage_rate"] <= 1
        assert layer["status"] in {
            "no_clear_incremental_value",
            "risk_value_only",
            "research_value",
            "weak_risk_value",
            "weak_opportunity_value",
        }
        assert "group_metrics" in layer

    assert time_safety["feature_release_or_source_lte_signal_date"] is True
    assert time_safety["violation_count"] == 0
    assert data_quality["uses_fixed_v5_1_exposure_level"] is True
    assert data_quality["uses_fixed_v5_10_risk_gradient"] is True
    assert data_quality["uses_fixed_v6_3_protection_score"] is True
    assert data_quality["uses_fixed_v6_5_two_axis_context"] is True
    assert data_quality["no_new_model"] is True
    assert data_quality["no_parameter_optimization"] is True
    assert constraints["does_not_create_new_model"] is True
    assert constraints["does_not_modify_mapper"] is True
    assert constraints["does_not_modify_exposure_level"] is True
    assert constraints["does_not_generate_position"] is True
    assert constraints["no_trade_signal"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_context_information_attribution(payload, Path(tmpdir) / "context_information_attribution.json")
        assert output.exists()

    print("test_context_information_attribution ok")


if __name__ == "__main__":
    main()
