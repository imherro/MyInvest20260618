from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.opportunity_risk_policy import (
    map_opportunity_risk_policy,
    map_row_policy,
)
from allocation_policy.policy_transition_matrix import build_opportunity_risk_policy_snapshot


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_policy_mapping_static_matrix_examples() -> None:
    assert map_opportunity_risk_policy("EARLY_RECOVERY", "LOW_RISK").policy_mode == "rebuild_risk"
    assert map_opportunity_risk_policy("BULL_EXPANSION", "LOW_RISK").policy_mode == "participate"
    assert map_opportunity_risk_policy("STRUCTURAL_ROTATION", "NORMAL").policy_mode == "participate_selectively"
    assert map_opportunity_risk_policy("STRUCTURAL_ROTATION", "CROWDED").policy_mode == "participate_with_control"
    assert map_opportunity_risk_policy("LATE_BULL", "HIGH_RISK").policy_mode == "protect_capital"
    assert map_opportunity_risk_policy("DEFENSIVE_REPAIR", "HIGH_RISK").policy_mode == "defensive"


def test_policy_payload_blocks_trading_outputs() -> None:
    payload = map_row_policy(
        {
            "opportunity_state": "STRUCTURAL_ROTATION",
            "risk_state": "CROWDED",
            "evidence": ["theme_persistence_high", "industry_breadth_narrow"],
        }
    )
    assert payload["policy_mode"] == "participate_with_control"
    assert "require_crowding_control" in payload["actions_allowed"]
    assert "aggressive_expansion" in payload["actions_blocked"]
    assert payload["constraints"]["no_allocation"] is True
    assert payload["constraints"]["no_trade"] is True


def test_snapshot_with_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_json(
            root / "opportunity_risk_snapshot.json",
            {
                "metadata": {
                    "engine": "V4.3 Market Opportunity vs Risk State Separation Engine",
                    "as_of": "20260707",
                },
                "current": {
                    "date": "20260707",
                    "opportunity_state": "LATE_BULL",
                    "risk_state": "CROWDED",
                    "combined_state": "LATE_BULL__CROWDED",
                    "evidence": ["trend_strong", "crowding_elevated"],
                    "interpretation": "fixture",
                },
                "historical_summary": {"replay_count": 4},
                "historical_replay": [
                    {"date": "20180131", "opportunity_state": "DEFENSIVE_REPAIR", "risk_state": "HIGH_RISK"},
                    {"date": "20200131", "opportunity_state": "EARLY_RECOVERY", "risk_state": "LOW_RISK"},
                    {"date": "20240131", "opportunity_state": "STRUCTURAL_ROTATION", "risk_state": "NORMAL"},
                    {"date": "20240630", "opportunity_state": "STRUCTURAL_ROTATION", "risk_state": "CROWDED"},
                ],
            },
        )
        payload = build_opportunity_risk_policy_snapshot(root)

    assert payload["metadata"]["engine"] == "V4.4 Opportunity-Risk Policy Mapping Validation"
    assert payload["current"]["policy_mode"] == "late_cycle_control"
    assert payload["summary"]["replay_count"] == 4
    assert payload["summary"]["policy_mode_distribution"]["defensive"]["count"] == 1
    assert payload["summary"]["policy_mode_distribution"]["participate_with_control"]["count"] == 1
    assert payload["data_quality"]["no_future_returns"] is True
    assert payload["constraints"]["no_etf_code"] is True
    assert payload["constraints"]["no_trade_signal"] is True


def test_snapshot_real_payload() -> None:
    payload = build_opportunity_risk_policy_snapshot()
    assert payload["summary"]["replay_count"] >= 100
    assert payload["current"]["policy_mode"] in {
        "rebuild_risk",
        "participate",
        "participate_selectively",
        "participate_with_control",
        "late_cycle_control",
        "protect_capital",
        "defensive",
        "watch_only",
    }
    assert payload["constraints"]["policy_mapping_only"] is True
    assert payload["constraints"]["no_asset_weight"] is True
    assert payload["constraints"]["no_parameter_optimization"] is True


if __name__ == "__main__":
    test_policy_mapping_static_matrix_examples()
    test_policy_payload_blocks_trading_outputs()
    test_snapshot_with_fixture()
    test_snapshot_real_payload()
    print("test_opportunity_risk_policy ok")
