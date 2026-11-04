from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_decision_audit import (
    build_exposure_decision_audit,
    write_exposure_decision_audit,
)
from adaptive_exposure.exposure_decision_context import DECISION_MODES, decision_context


def main() -> None:
    payload = build_exposure_decision_audit()
    summary = payload["summary"]
    mode_stats = payload["mode_stats"]
    separation = payload["separation_review"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert payload["metadata"]["engine"] == "V6.2 Adaptive Exposure Decision Layer Design Audit"
    assert summary["joined_sample_count"] == 115
    assert set(mode_stats) == set(DECISION_MODES)
    assert mode_stats["SELECTIVE_PARTICIPATION"]["sample_count"] == 70
    assert mode_stats["PROTECTED_PARTICIPATION"]["sample_count"] == 6
    assert summary["risk_separation"] == "weak"
    assert summary["opportunity_separation"] == "weak"
    assert summary["conclusion"] == "decision_context_design_not_validated"
    assert summary["ready_for_mapper_change"] is False
    assert summary["ready_for_exposure_change"] is False
    assert separation["caution_vs_participation_risk_lift"] < 0.05

    sample_context = decision_context(
        {
            "risk_gradient_bucket": "high_risk",
            "risk_gradient_score": 70,
            "analysis_context": {
                "opportunity_state": "EARLY_RECOVERY",
                "market_phase": "EARLY_CYCLE",
                "risk_state": "CROWDED",
            },
        }
    )
    assert sample_context["decision_mode"] == "PROTECTED_PARTICIPATION"
    assert sample_context["research_label_only"] is True

    assert time_safety["feature_release_or_source_lte_signal_date"] is True
    assert time_safety["violation_count"] == 0
    assert data_quality["decision_modes_are_research_labels_only"] is True
    assert data_quality["no_parameter_optimization"] is True
    assert constraints["does_not_modify_mapper"] is True
    assert constraints["does_not_modify_exposure_level"] is True
    assert constraints["does_not_generate_position"] is True
    assert constraints["no_etf_code"] is True
    assert constraints["no_trade_signal"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_exposure_decision_audit(payload, Path(tmpdir) / "exposure_decision_audit.json")
        assert output.exists()

    print("test_exposure_decision_audit ok")


if __name__ == "__main__":
    main()
