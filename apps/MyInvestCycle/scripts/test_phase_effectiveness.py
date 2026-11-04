from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.phase_effectiveness_audit import build_phase_effectiveness_audit
from allocation_policy.phase_transition_analysis import analyze_phase_transitions


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_transition_analysis_flags_unexpected_paths() -> None:
    rows = [
        {"date": "20240101", "phase": "EARLY_CYCLE"},
        {"date": "20240201", "phase": "ROTATION"},
        {"date": "20240301", "phase": "CONTRACTION"},
        {"date": "20240401", "phase": "LATE_CYCLE"},
    ]
    payload = analyze_phase_transitions(rows)
    assert payload["transition_count"] == 3
    assert payload["unexpected_transition_count"] >= 1


def test_phase_effectiveness_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        phase_rows = [
            {"date": "20180101", "phase": "ROTATION"},
            {"date": "20180201", "phase": "EARLY_CYCLE"},
            {"date": "20180301", "phase": "CONTRACTION"},
            {"date": "20240101", "phase": "LATE_CYCLE"},
        ]
        validation_rows = [
            {
                "date": "20180101",
                "future_window_complete": True,
                "structural_state": "BROAD_BULL",
                "combined_state": "STRUCTURAL_ROTATION__CROWDED",
                "policy_mode": "participate_with_control",
                "future_environment": "drawdown_stress",
                "future_flags": {"high_risk_event": True, "strong_opportunity_event": False},
                "future_metrics": {"max_drawdown_120d": -0.2, "forward_return_120d": -0.08},
            },
            {
                "date": "20180201",
                "future_window_complete": True,
                "structural_state": "BROAD_BULL",
                "combined_state": "EARLY_RECOVERY__NORMAL",
                "policy_mode": "rebuild_risk",
                "future_environment": "drawdown_stress",
                "future_flags": {"high_risk_event": True, "strong_opportunity_event": False},
                "future_metrics": {"max_drawdown_120d": -0.18, "forward_return_120d": -0.04},
            },
            {
                "date": "20180301",
                "future_window_complete": True,
                "structural_state": "WEAK_MARKET",
                "combined_state": "EARLY_RECOVERY__CROWDED",
                "policy_mode": "participate_with_control",
                "future_environment": "range_mixed",
                "future_flags": {"high_risk_event": False, "strong_opportunity_event": False},
                "future_metrics": {"max_drawdown_120d": -0.04, "forward_return_120d": 0.02},
            },
        ]
        _write_json(
            root / "market_phase_snapshot.json",
            {
                "metadata": {"engine": "fixture", "as_of": "20240301"},
                "historical_summary": {
                    "phase_distribution": {"EXPANSION": {"count": 0}, "replay_count": 4},
                },
                "historical_replay": phase_rows,
            },
        )
        _write_json(
            root / "policy_effectiveness.json",
            {
                "summary": {
                    "policy_usefulness": {
                        "structural_high_risk_rate_spread": 0.2,
                        "opportunity_risk_high_risk_rate_spread": 0.4,
                        "policy_high_risk_rate_spread": 0.3,
                    }
                },
                "validation_rows": validation_rows,
            },
        )
        payload = build_phase_effectiveness_audit(root)

    assert payload["metadata"]["engine"] == "V4.7 Market Phase Effectiveness Audit & Calibration Review"
    assert payload["summary"]["usable_rows"] == 3
    assert payload["summary"]["review_item_count"] >= 1
    assert payload["constraints"]["does_not_modify_v4_6_phase_rules"] is True


def test_phase_effectiveness_real_payload() -> None:
    payload = build_phase_effectiveness_audit()
    assert payload["summary"]["usable_rows"] >= 100
    assert payload["summary"]["model_comparison"]["phase_high_risk_rate_spread"] is not None
    assert payload["transition_analysis"]["transition_count"] >= 100
    assert payload["constraints"]["no_trade_signal"] is True


if __name__ == "__main__":
    test_transition_analysis_flags_unexpected_paths()
    test_phase_effectiveness_fixture()
    test_phase_effectiveness_real_payload()
    print("test_phase_effectiveness ok")
