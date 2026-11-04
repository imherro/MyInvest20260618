from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.risk_gradient_candidate_rules import (
    build_risk_gradient_candidate_rules,
    write_risk_gradient_candidate_rules,
)


def main() -> None:
    payload = build_risk_gradient_candidate_rules()
    summary = payload["summary"]
    candidates = payload["candidate_rules"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert payload["metadata"]["engine"] == "V5.13 Risk Gradient Minimal Rule Candidate Audit"
    assert summary["source_rows"] == 115
    assert summary["candidate_count"] == 5
    assert summary["primary_research_candidate_count"] == 2
    assert summary["ready_for_rule_count"] == 0
    assert summary["ready_for_mapper_change"] is False
    assert summary["conclusion"] == "minimal_candidates_found_but_none_rule_ready"

    by_candidate = {item["candidate"]: item for item in candidates}
    assert "CROWDED" in by_candidate
    assert "EARLY_CYCLE+CROWDED" in by_candidate
    assert by_candidate["CROWDED"]["research_tier"] == "primary_research_candidate"
    assert by_candidate["EARLY_CYCLE+CROWDED"]["research_tier"] == "primary_research_candidate"
    assert all(item["ready_for_rule"] is False for item in candidates)
    assert all(item["trigger"] == "risk_gradient_bucket == high_risk" for item in candidates)

    assert time_safety["feature_release_or_source_lte_signal_date"] is True
    assert time_safety["violation_count"] == 0
    assert time_safety["future_labels_used_for_validation_only"] is True

    assert data_quality["uses_v5_12_positive_conditions_only"] is True
    assert data_quality["candidate_count_limited"] is True
    assert data_quality["does_not_search_condition_space"] is True
    assert data_quality["risk_gradient_score_reused_not_reweighted"] is True
    assert constraints["no_formal_rule_output"] is True
    assert constraints["does_not_modify_mapper"] is True
    assert constraints["no_etf_code"] is True
    assert constraints["no_trade_signal"] is True
    assert constraints["no_order_generation"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_risk_gradient_candidate_rules(payload, Path(tmpdir) / "risk_gradient_candidate_rules.json")
        assert output.exists()

    print("test_risk_gradient_candidate_rules ok")


if __name__ == "__main__":
    main()
