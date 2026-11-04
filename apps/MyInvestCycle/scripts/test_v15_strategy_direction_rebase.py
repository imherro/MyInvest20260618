from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_strategy_direction_rebase,
    validate_v15_strategy_direction_rebase,
    write_v15_strategy_direction_rebase,
)


def main() -> None:
    payload = build_v15_strategy_direction_rebase()
    metadata = payload["metadata"]
    summary = payload["summary"]
    frozen = payload["frozen_tracks"]["v12_v14_governance_shadow"]
    hypotheses = payload["new_strategy_hypotheses"]
    constraints = payload["constraints"]
    audit = payload["audit"]

    assert metadata["engine"] == "V15.0 Mainline Outcome-Oriented Strategy Rebase"
    assert metadata["base_commit"] == "58b5ab83398b0f6ed2adf5b4027f782fbd4b5303"
    assert summary["phase"] == "V15"
    assert summary["mainline_direction"] == "outcome_oriented_strategy_rebase"
    assert summary["direction_status"] == "rebase_declared"
    assert summary["primary_objective"] == "maximize_return_and_alpha"
    assert summary["secondary_objective"] == "control_max_drawdown"
    assert summary["must_backtest_before_strategy_claim"] is True
    assert summary["production_trade_enabled"] is False
    assert summary["broker_connection_enabled"] is False
    assert summary["real_order_generation_enabled"] is False

    assert frozen["status"] == "frozen_as_infrastructure"
    assert frozen["not_main_alpha_strategy"] is True
    assert frozen["not_portfolio_engine"] is True
    assert frozen["not_trade_engine"] is True
    assert "main_alpha_claim" in frozen["disallowed_future_use"]

    assert set(hypotheses) == {"macro_cycle", "drawdown_context", "structural_bull", "mainline_rotation"}
    assert all(item["must_backtest"] is True for item in hypotheses.values())

    assert constraints["direction_rebase_only"] is True
    assert constraints["does_not_run_backtest"] is True
    assert constraints["does_not_generate_position"] is True
    assert constraints["does_not_generate_etf_mapping"] is True
    assert constraints["does_not_generate_portfolio_weight"] is True
    assert constraints["does_not_generate_allocation"] is True
    assert constraints["does_not_generate_trade_signal"] is True
    assert constraints["does_not_create_order"] is True
    assert constraints["does_not_connect_broker"] is True
    assert constraints["production_trade_enabled"] is False

    forbidden_joined = " ".join(payload["forbidden_outputs"])
    for forbidden in ("trade_signal", "portfolio_weight", "etf_mapping", "broker_order"):
        assert forbidden in forbidden_joined
    assert audit["audit_status"] == "passed"
    assert validate_v15_strategy_direction_rebase(payload)["audit_status"] == "passed"

    joined = " ".join(str(value) for value in payload.values())
    for code in ("510" + "300", "510" + "500", "159" + "915"):
        assert code not in joined

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_v15_strategy_direction_rebase(payload, Path(tmpdir) / "v15_strategy_direction_rebase.json")
        assert output.exists()

    print("test_v15_strategy_direction_rebase ok")


if __name__ == "__main__":
    main()
