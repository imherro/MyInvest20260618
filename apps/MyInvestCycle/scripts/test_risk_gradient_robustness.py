from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.risk_gradient_robustness import (
    FIXED_RISK_THRESHOLDS,
    REQUIRED_PERIODS,
    build_risk_gradient_robustness,
    write_risk_gradient_robustness,
)


def main() -> None:
    payload = build_risk_gradient_robustness()
    summary = payload["summary"]
    periods = payload["period_analysis"]
    robustness = payload["robustness"]
    threshold = payload["threshold_consistency"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    data_quality = payload["data_quality"]

    assert payload["metadata"]["engine"] == "V5.11 Risk Gradient Robustness & Stability Audit"
    assert summary["source_rows"] == 115
    assert summary["overall_high_risk_lift"] > 0.05
    assert summary["period_consistency"] in {"insufficient_evidence", "weak"}
    assert summary["conclusion"] == "overall_edge_visible_but_not_robust"
    assert summary["ready_for_mapper_change"] is False

    assert [period["period"] for period in periods] == [period[0] for period in REQUIRED_PERIODS]
    assert any(period["status"] == "positive" for period in periods)
    assert any(period["status"] == "negative" for period in periods)
    assert robustness["positive_period_count"] == 1
    assert robustness["negative_period_count"] == 1

    assert threshold["fixed_thresholds"] == FIXED_RISK_THRESHOLDS
    assert threshold["thresholds_were_not_optimized"] is True
    assert threshold["mismatch_count"] == 0

    assert time_safety["feature_release_or_source_lte_signal_date"] is True
    assert time_safety["violation_count"] == 0
    assert time_safety["future_labels_used_for_validation_only"] is True
    assert data_quality["risk_gradient_score_reused_not_reweighted"] is True
    assert data_quality["fixed_thresholds_reused"] is True
    assert data_quality["no_parameter_optimization"] is True

    assert constraints["does_not_modify_gradient_weight"] is True
    assert constraints["does_not_modify_threshold"] is True
    assert constraints["does_not_modify_mapper"] is True
    assert constraints["does_not_modify_policy"] is True
    assert constraints["no_etf_code"] is True
    assert constraints["no_trade_signal"] is True
    assert constraints["no_order_generation"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_risk_gradient_robustness(payload, Path(tmpdir) / "risk_gradient_robustness.json")
        assert output.exists()

    print("test_risk_gradient_robustness ok")


if __name__ == "__main__":
    main()
