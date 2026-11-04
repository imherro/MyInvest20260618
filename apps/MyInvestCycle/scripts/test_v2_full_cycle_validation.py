from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.full_cycle_validation import build_data_coverage_audit, run_full_cycle_validation


def main() -> None:
    audit = build_data_coverage_audit(desired_start="20150101", desired_end="20260708")
    assert audit["policy"]["do_not_fabricate_history"] is True
    assert audit["policy"]["do_not_treat_partial_cache_as_full_cycle"] is True
    assert "macro" in audit["modules"]
    assert "industry_opportunity" in audit["modules"]
    assert "etf_proxy" in audit["modules"]

    payload = run_full_cycle_validation(desired_start="20150101", desired_end="20260708")
    assert payload["constraints"]["no_strategy_rule_change"] is True
    assert payload["constraints"]["no_threshold_tuning"] is True
    assert payload["constraints"]["walk_forward"] is True
    assert payload["metadata"]["full_cycle_claim"] == payload["coverage_audit"]["can_cover_desired_window"]
    assert payload["metadata"]["validation_window"]["start"] >= payload["coverage_audit"]["operational_validation_window"]["start"]
    comparison = payload["comparison"]
    for key in (
        "v2_refined_structural_policy",
        "v2_baseline",
        "benchmark_510300",
        "benchmark_510500",
        "buy_hold_equal_510300_510500",
        "old_s1",
        "m2_macro_style",
    ):
        assert key in comparison, key
        assert "annualized_return" in comparison[key], key
        assert "max_drawdown" in comparison[key], key
    assert payload["refined_policy"]["signals"]
    assert payload["v2_baseline"]["signals"]
    print("test_v2_full_cycle_validation ok")


if __name__ == "__main__":
    main()
