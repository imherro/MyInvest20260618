from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.full_cycle_backtest import run_full_cycle_backtest


def main() -> None:
    payload = run_full_cycle_backtest(desired_start="20150105", desired_end="20150430")
    assert payload["metadata"]["walk_forward"] is True
    assert payload["metadata"]["no_lookahead_bias"] is True
    assert payload["constraints"]["no_strategy_rule_change"] is True
    assert payload["constraints"]["no_threshold_tuning"] is True
    assert payload["constraints"]["no_allocation_change"] is True
    assert payload["constraints"]["no_new_factor"] is True
    assert payload["data_quality"]["macro_gap_policy"]["confidence_penalty"] == 0.1
    assert payload["metadata"]["validation_window"]["start"] >= "20150105"
    assert payload["equity_curve"]
    assert payload["signals"]["v2_structural_refined"]
    for key in (
        "v2_current",
        "v2_structural_refined",
        "v2_baseline",
        "benchmark_510300",
        "benchmark_510500",
        "buy_hold_equal_510300_510500",
        "old_s1",
        "m2_macro_style",
    ):
        assert key in payload["comparison"], key
        assert "annualized_return" in payload["comparison"][key], key
        assert "max_drawdown" in payload["comparison"][key], key
    assert "2015_bull_bear" in payload["period_attribution"]
    assert "STRUCTURAL_BULL_ROTATION" in payload["structural_bull_contribution"]
    print("test_v2_full_cycle_backtest ok")


if __name__ == "__main__":
    main()
