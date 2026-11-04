from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.balanced_candidate_failure_analysis import build_balanced_candidate_failure_analysis


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_balanced_candidate_failure_analysis_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_json(
            root / "balanced_context_audit.json",
            {
                "metadata": {"engine": "V5.4 fixture", "as_of": "20260707"},
                "summary": {"candidate_quality": {"status": "candidate_not_ready_for_mapper_change"}},
            },
        )
        _write_json(
            root / "exposure_context_analysis.json",
            {
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
                    {"reason": "price_extension_high", "count": 6, "failure_rate": 0.5},
                    {"reason": "trend_strong", "count": 6, "missed_opportunity_rate": 0.333333},
                ],
            },
        )
        payload = build_balanced_candidate_failure_analysis(root)

    assert payload["metadata"]["engine"] == "V5.5 Balanced Candidate Failure Attribution"
    assert payload["candidate_attribution"]["BALANCED_RISK"]["sample_count"] == 6
    assert payload["candidate_attribution"]["BALANCED_OPPORTUNITY"]["sample_count"] == 6
    assert payload["summary"]["ready_for_rule_change"] is False
    assert payload["constraints"]["does_not_modify_mapper"] is True
    assert payload["constraints"]["no_trade_signal"] is True


def test_balanced_candidate_failure_analysis_real_payload() -> None:
    payload = build_balanced_candidate_failure_analysis()
    assert payload["summary"]["ready_for_rule_change"] is False
    assert payload["candidate_attribution"]["BALANCED_RISK"]["sample_count"] >= 1
    assert payload["candidate_attribution"]["BALANCED_OPPORTUNITY"]["sample_count"] >= 1
    assert payload["data_quality"]["needs_numeric_context_enrichment"] is True
    assert payload["constraints"]["no_return_optimization"] is True


if __name__ == "__main__":
    test_balanced_candidate_failure_analysis_fixture()
    test_balanced_candidate_failure_analysis_real_payload()
    print("test_balanced_candidate_failure_analysis ok")
