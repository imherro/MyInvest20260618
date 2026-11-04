from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_policy_mapper import decision_to_payload, map_policy_to_exposure
from adaptive_exposure.exposure_schema import EXPOSURE_LEVELS
from adaptive_exposure.exposure_simulator import build_exposure_simulation


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_mapper_keeps_qualitative_exposure_only() -> None:
    decision = map_policy_to_exposure(
        {
            "policy_mode": "participate",
            "opportunity_state": "BULL_EXPANSION",
            "risk_state": "CROWDED",
            "evidence": ["trend_strong"],
        },
        {"phase": "LATE_CYCLE"},
    )
    payload = decision_to_payload(decision)
    assert payload["exposure_level"] in EXPOSURE_LEVELS
    assert payload["exposure_level"] == "BALANCED"
    text = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("510300", "510500", "159915", "511880", "%"):
        assert forbidden not in text
    assert payload["constraints"]["simulation_only"] is True
    assert payload["constraints"]["no_trade"] is True


def test_exposure_simulation_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_json(
            root / "opportunity_risk_policy.json",
            {
                "metadata": {"engine": "fixture-policy", "as_of": "20260707"},
                "current": {
                    "date": "20260707",
                    "policy_mode": "late_cycle_control",
                    "opportunity_state": "LATE_BULL",
                    "risk_state": "CROWDED",
                    "evidence": ["crowding_high"],
                },
                "historical_replay": [
                    {
                        "date": "20240101",
                        "policy_mode": "participate",
                        "opportunity_state": "BULL_EXPANSION",
                        "risk_state": "LOW_RISK",
                    },
                    {
                        "date": "20240201",
                        "policy_mode": "protect_capital",
                        "opportunity_state": "DEFENSIVE_REPAIR",
                        "risk_state": "HIGH_RISK",
                    },
                    {
                        "date": "20240301",
                        "policy_mode": "late_cycle_control",
                        "opportunity_state": "LATE_BULL",
                        "risk_state": "CROWDED",
                    },
                ],
            },
        )
        _write_json(
            root / "market_phase_snapshot.json",
            {
                "metadata": {"engine": "fixture-phase"},
                "current": {"phase": "LATE_CYCLE"},
                "historical_replay": [
                    {"date": "20240101", "phase": "EXPANSION"},
                    {"date": "20240201", "phase": "CONTRACTION"},
                    {"date": "20240301", "phase": "LATE_CYCLE"},
                ],
            },
        )
        _write_json(
            root / "policy_effectiveness.json",
            {
                "validation_rows": [
                    {
                        "date": "20240101",
                        "future_window_complete": True,
                        "future_environment": "strong_upside",
                        "future_flags": {"strong_opportunity_event": True, "high_risk_event": False},
                    },
                    {
                        "date": "20240201",
                        "future_window_complete": True,
                        "future_environment": "drawdown_stress",
                        "future_flags": {"high_risk_event": True, "future_drawdown_gt_15": True},
                    },
                    {
                        "date": "20240301",
                        "future_window_complete": True,
                        "future_environment": "strong_upside",
                        "future_flags": {"strong_opportunity_event": True, "high_risk_event": False},
                    },
                ]
            },
        )
        payload = build_exposure_simulation(root)

    assert payload["metadata"]["engine"] == "V5.1 Adaptive Exposure Policy Simulation Foundation"
    assert payload["current"]["exposure_level"] == "LOW"
    assert payload["summary"]["replay_count"] == 3
    assert payload["summary"]["audit"]["usable_rows"] == 3
    assert payload["summary"]["audit"]["opportunity_miss_count"] >= 1
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_position_sizing"] is True


def test_exposure_simulation_real_payload() -> None:
    payload = build_exposure_simulation()
    assert payload["summary"]["replay_count"] >= 100
    assert payload["current"]["exposure_level"] in EXPOSURE_LEVELS
    assert payload["summary"]["audit"]["usable_rows"] >= 100
    assert payload["constraints"]["simulation_only"] is True
    assert payload["constraints"]["no_etf_code"] is True
    assert payload["constraints"]["no_return_optimization"] is True


if __name__ == "__main__":
    test_mapper_keeps_qualitative_exposure_only()
    test_exposure_simulation_fixture()
    test_exposure_simulation_real_payload()
    print("test_exposure_simulation ok")
