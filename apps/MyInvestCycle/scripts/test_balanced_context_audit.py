from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.balanced_context_audit import (
    build_balanced_context_audit,
    classify_candidate_context,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_candidate_context_classification() -> None:
    assert classify_candidate_context({"usable_rows": 5, "failure_rate": 0.4}) == "BALANCED_RISK"
    assert classify_candidate_context({"usable_rows": 5, "failure_rate": 0.0, "missed_opportunity_rate": 0.3}) == "BALANCED_OPPORTUNITY"
    assert classify_candidate_context({"usable_rows": 2, "failure_rate": 0.8, "missed_opportunity_rate": 0.0}) == "BALANCED_NEUTRAL"


def test_balanced_context_audit_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_json(
            root / "exposure_context_analysis.json",
            {
                "metadata": {"engine": "V5.3 fixture", "as_of": "20260707"},
                "summary": {"balanced_usable_rows": 12},
                "context_comparison": [
                    {
                        "opportunity_state": "EARLY_RECOVERY",
                        "risk_state": "NORMAL",
                        "market_phase": "EARLY_CYCLE",
                        "usable_rows": 6,
                        "failure_rate": 0.5,
                        "missed_opportunity_rate": 0.0,
                        "future_high_risk_rate": 0.5,
                    },
                    {
                        "opportunity_state": "STRUCTURAL_ROTATION",
                        "risk_state": "NORMAL",
                        "market_phase": "ROTATION",
                        "usable_rows": 6,
                        "failure_rate": 0.0,
                        "missed_opportunity_rate": 0.333333,
                        "future_high_risk_rate": 0.0,
                    },
                ],
                "reason_flag_analysis": [
                    {"reason": "trend_strong", "count": 6, "failure_rate": 0.0, "missed_opportunity_rate": 0.333333},
                    {"reason": "price_extension_high", "count": 6, "failure_rate": 0.5, "missed_opportunity_rate": 0.0},
                ],
            },
        )
        payload = build_balanced_context_audit(root)

    assert payload["metadata"]["engine"] == "V5.4 Balanced Context Candidate State Audit"
    assert payload["candidate_states"]["BALANCED_RISK"]["sample_count"] == 6
    assert payload["candidate_states"]["BALANCED_OPPORTUNITY"]["sample_count"] == 6
    assert payload["summary"]["candidate_quality"]["ready_for_formal_rule"] is False
    assert payload["constraints"]["research_labels_only"] is True
    assert payload["constraints"]["no_trade_signal"] is True


def test_balanced_context_audit_real_payload() -> None:
    payload = build_balanced_context_audit()
    assert payload["summary"]["balanced_usable_rows"] >= 100
    assert payload["summary"]["candidate_quality"]["ready_for_formal_rule"] is False
    assert "BALANCED_RISK" in payload["candidate_states"]
    assert payload["data_quality"]["research_labels_only"] is True
    assert payload["constraints"]["does_not_add_formal_exposure_levels"] is True


if __name__ == "__main__":
    test_candidate_context_classification()
    test_balanced_context_audit_fixture()
    test_balanced_context_audit_real_payload()
    print("test_balanced_context_audit ok")
