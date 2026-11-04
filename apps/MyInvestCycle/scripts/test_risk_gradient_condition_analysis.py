from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.risk_gradient_condition_analysis import (
    FIXED_RISK_THRESHOLDS,
    build_risk_gradient_condition_analysis,
    write_risk_gradient_condition_analysis,
)


def _find(items: list[dict], condition: str) -> dict:
    for item in items:
        if item.get("condition") == condition:
            return item
    raise AssertionError(f"Missing condition {condition}")


def main() -> None:
    payload = build_risk_gradient_condition_analysis()
    summary = payload["summary"]
    dimensions = payload["dimension_analysis"]
    composites = payload["composite_analysis"]
    threshold = payload["threshold_consistency"]
    time_safety = payload["time_safety"]
    constraints = payload["constraints"]
    data_quality = payload["data_quality"]

    assert payload["metadata"]["engine"] == "V5.12 Risk Gradient Conditional Validation"
    assert summary["source_rows"] == 115
    assert summary["ready_for_mapper_change"] is False
    assert summary["conclusion"] == "conditional_edge_visible_but_not_rule_ready"
    assert summary["positive_condition_count"] >= 3
    assert summary["insufficient_condition_count"] > summary["evaluated_condition_count"]

    crowded = _find(dimensions["risk_state"], "CROWDED")
    assert crowded["risk_gradient_edge"] == "positive"
    assert crowded["high_risk_lift"] > 0.05

    early_cycle = _find(dimensions["market_phase"], "EARLY_CYCLE")
    assert early_cycle["risk_gradient_edge"] == "positive"
    assert early_cycle["high_risk_lift"] > 0.05

    early_crowded = _find(composites["market_phase+risk_state"], "EARLY_CYCLE+CROWDED")
    assert early_crowded["risk_gradient_edge"] == "positive"
    assert early_crowded["confidence"] in {"low_medium", "medium"}

    early_recovery_crowded = _find(composites["opportunity_state+risk_state"], "EARLY_RECOVERY+CROWDED")
    assert early_recovery_crowded["risk_gradient_edge"] == "flat"

    assert threshold["fixed_thresholds"] == FIXED_RISK_THRESHOLDS
    assert threshold["thresholds_were_not_optimized"] is True
    assert threshold["mismatch_count"] == 0
    assert time_safety["feature_release_or_source_lte_signal_date"] is True
    assert time_safety["violation_count"] == 0
    assert time_safety["future_labels_used_for_validation_only"] is True

    assert data_quality["risk_gradient_score_reused_not_reweighted"] is True
    assert data_quality["fixed_thresholds_reused"] is True
    assert data_quality["conditions_are_descriptive_not_rules"] is True
    assert constraints["does_not_modify_gradient_weight"] is True
    assert constraints["does_not_modify_threshold"] is True
    assert constraints["does_not_modify_mapper"] is True
    assert constraints["no_etf_code"] is True
    assert constraints["no_trade_signal"] is True
    assert constraints["no_order_generation"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_risk_gradient_condition_analysis(payload, Path(tmpdir) / "risk_gradient_condition_analysis.json")
        assert output.exists()

    print("test_risk_gradient_condition_analysis ok")


if __name__ == "__main__":
    main()
