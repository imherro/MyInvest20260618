from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_effectiveness import build_exposure_effectiveness


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_exposure_effectiveness_fixture_flags_wide_bucket() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        rows = [
            {
                "date": "20240101",
                "exposure_level": "BALANCED",
                "policy_mode": "participate_with_control",
                "opportunity_state": "STRUCTURAL_ROTATION",
                "risk_state": "CROWDED",
                "market_phase": "ROTATION",
                "future_window_complete": True,
                "future_environment": "drawdown_stress",
                "future_flags": {"high_risk_event": True, "future_drawdown_gt_15": True},
                "contradictions": [{"type": "large_drawdown_with_non_defensive_level"}],
            },
            {
                "date": "20240201",
                "exposure_level": "BALANCED",
                "policy_mode": "participate_with_control",
                "opportunity_state": "STRUCTURAL_ROTATION",
                "risk_state": "CROWDED",
                "market_phase": "ROTATION",
                "future_window_complete": True,
                "future_environment": "range_mixed",
                "future_flags": {},
                "contradictions": [],
            },
            {
                "date": "20240301",
                "exposure_level": "LOW",
                "policy_mode": "late_cycle_control",
                "opportunity_state": "LATE_BULL",
                "risk_state": "CROWDED",
                "market_phase": "LATE_CYCLE",
                "future_window_complete": True,
                "future_environment": "strong_upside",
                "future_flags": {"strong_opportunity_event": True},
                "contradictions": [{"type": "strong_opportunity_with_low_exposure_level"}],
            },
        ]
        _write_json(
            root / "exposure_simulation.json",
            {
                "metadata": {"engine": "V5.1 fixture", "as_of": "20260707"},
                "current": {"exposure_level": "LOW"},
                "historical_replay": rows,
            },
        )
        payload = build_exposure_effectiveness(root)

    assert payload["metadata"]["engine"] == "V5.2 Exposure Level Effectiveness Audit & Calibration Review"
    assert payload["summary"]["level_effectiveness"]["BALANCED"]["total_count"] == 2
    assert payload["summary"]["distribution_review"]["dominant_level"] == "BALANCED"
    assert payload["summary"]["ordering_review"]["status"] == "ordering_review_needed"
    assert payload["constraints"]["does_not_modify_v5_1_rules"] is True
    assert payload["constraints"]["no_trade_signal"] is True


def test_exposure_effectiveness_real_payload() -> None:
    payload = build_exposure_effectiveness()
    assert payload["summary"]["replay_count"] >= 100
    assert payload["summary"]["usable_rows"] >= 100
    assert "BALANCED" in payload["summary"]["level_effectiveness"]
    assert payload["summary"]["distribution_review"]["dominant_level"] == "BALANCED"
    assert payload["summary"]["high_offensive_absence"]["missing_positive_levels"]
    assert payload["data_quality"]["does_not_modify_mapper"] is True
    assert payload["constraints"]["no_return_optimization"] is True


if __name__ == "__main__":
    test_exposure_effectiveness_fixture_flags_wide_bucket()
    test_exposure_effectiveness_real_payload()
    print("test_exposure_effectiveness ok")
