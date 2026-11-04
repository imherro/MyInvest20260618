from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_macro_drawdown_robustness_result,
    validate_v15_macro_drawdown_robustness_result,
    write_v15_macro_drawdown_robustness_result,
)


def main() -> None:
    payload = build_v15_macro_drawdown_robustness_result()
    summary = payload["summary"]
    grid = payload["parameter_grid"]
    walk_forward = payload["walk_forward"]
    quality = payload["data_quality"]
    constraints = payload["constraints"]
    formal = payload["formal_evaluation"]

    assert payload["phase"] == "V15.4"
    assert payload["validation_status"] == "completed"
    assert payload["research_backtest_only"] is True
    assert payload["not_production_signal"] is True
    assert payload["no_real_trade_order"] is True
    assert payload["uses_t_plus_one_execution"] is True
    assert summary["parameter_variants"] == 9
    assert len(grid) == 9
    assert {row["variant_id"] for row in grid} == {
        f"t{threshold:03d}_e{exposure:03d}"
        for threshold in (75, 100, 125)
        for exposure in (75, 100, 125)
    }
    assert 1 <= summary["default_variant_rank"] <= 9
    assert summary["strict_point_in_time_status"] == "unverified"
    assert isinstance(summary["parameter_neighborhood_stable"], bool)
    assert isinstance(summary["default_parameter_preferred"], bool)
    assert summary["promotion_ready"] is False
    assert summary["walk_forward_cost_bps"] == 15
    assert summary["formal_evaluation_status"] == "failed"
    assert formal["status"] == "failed"
    assert formal["decision"] == "reject_promotion"
    assert formal["return_and_benchmark_index"] == "H00300.CSI"
    assert formal["transaction_cost_bps"] == 15
    assert formal["checks"]["full_period_beats_total_return_benchmark"] is False
    assert formal["checks"]["strict_point_in_time_verified"] is False
    assert quality["default_reproduction_within_tolerance"] is True
    assert quality["t_plus_one_reapplied_for_every_variant"] is True
    assert quality["training_uses_only_dates_before_test_year"] is True
    assert quality["phase_history_strict_point_in_time_not_independently_verified"] is True
    assert len(walk_forward["selections"]) >= 5
    for selection in walk_forward["selections"]:
        assert selection["training_end"] < f"{selection['test_year']}0101"
    for cost in ("0", "5", "10", "15"):
        assert cost in payload["default_cost_sensitivity"]
        assert cost in payload["walk_forward_cost_sensitivity"]
    assert constraints["no_broker_connection"] is True
    assert constraints["no_order_generation"] is True
    assert constraints["not_intraday_signal"] is True
    assert constraints["not_production_trade_signal"] is True
    assert constraints["no_current_position_recommendation"] is True
    assert validate_v15_macro_drawdown_robustness_result(payload)["audit_status"] == "passed"

    for forbidden in ("trade_signal", "portfolio_weight", "broker_order", "real_order"):
        assert forbidden not in payload

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_v15_macro_drawdown_robustness_result(
            payload,
            Path(tmpdir) / "v15_macro_drawdown_robustness_result.json",
        )
        assert output.exists()

    print("test_v15_macro_drawdown_robustness ok")


if __name__ == "__main__":
    main()
