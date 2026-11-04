from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_context_analysis import (
    build_exposure_context_analysis,
    classify_balanced_outcome,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_balanced_outcome_classification() -> None:
    assert classify_balanced_outcome({"future_flags": {"high_risk_event": True}}) == "BALANCED_FAILURE"
    assert classify_balanced_outcome({"future_flags": {"future_drawdown_gt_15": True}}) == "BALANCED_FAILURE"
    assert classify_balanced_outcome({"future_flags": {"strong_opportunity_event": True}}) == "BALANCED_MISSED_OPPORTUNITY"
    assert classify_balanced_outcome({"future_flags": {}}) == "BALANCED_NEUTRAL"


def test_exposure_context_fixture() -> None:
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
                "reasons": ["macro_recovery", "single_theme_concentration"],
                "future_window_complete": True,
                "future_environment": "drawdown_stress",
                "future_flags": {"high_risk_event": True},
            },
            {
                "date": "20240201",
                "exposure_level": "BALANCED",
                "policy_mode": "participate_with_control",
                "opportunity_state": "STRUCTURAL_ROTATION",
                "risk_state": "CROWDED",
                "market_phase": "ROTATION",
                "reasons": ["macro_recovery", "single_theme_concentration"],
                "future_window_complete": True,
                "future_environment": "strong_uptrend",
                "future_flags": {"strong_opportunity_event": True},
            },
            {
                "date": "20240301",
                "exposure_level": "LOW",
                "policy_mode": "late_cycle_control",
                "future_window_complete": True,
                "future_flags": {},
            },
        ]
        _write_json(
            root / "exposure_simulation.json",
            {
                "metadata": {"engine": "V5.1 fixture", "as_of": "20260707"},
                "historical_replay": rows,
            },
        )
        payload = build_exposure_context_analysis(root)

    assert payload["metadata"]["engine"] == "V5.3 Exposure Context Decomposition Audit"
    assert payload["summary"]["balanced_count"] == 2
    assert payload["summary"]["balanced_share_of_all"] == 0.666667
    assert payload["balanced_subgroups"]["BALANCED_FAILURE"]["count"] == 1
    assert payload["balanced_subgroups"]["BALANCED_MISSED_OPPORTUNITY"]["count"] == 1
    assert payload["constraints"]["does_not_modify_v5_1_rules"] is True
    assert payload["constraints"]["no_trade_signal"] is True


def test_exposure_context_real_payload() -> None:
    payload = build_exposure_context_analysis()
    assert payload["summary"]["balanced_count"] >= 100
    assert payload["summary"]["balanced_share_of_all"] >= 0.6
    assert payload["summary"]["split_candidates"]["recommendation"] in {
        "split_balanced_before_mapper_changes",
        "balanced_split_not_yet_supported",
    }
    assert payload["data_quality"]["balanced_bucket_only"] is True
    assert payload["constraints"]["balanced_analysis_only"] is True


if __name__ == "__main__":
    test_balanced_outcome_classification()
    test_exposure_context_fixture()
    test_exposure_context_real_payload()
    print("test_exposure_context_analysis ok")
