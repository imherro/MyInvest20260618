from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_context_state_audit import (
    build_exposure_context_state_audit,
    classify_context_state,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _source_trace(date: str, context: dict[str, object]) -> dict[str, object]:
    return {
        field: {
            "available": value is not None,
            "value": value,
            "source": "fixture",
            "release_date": date,
            "effective_date": date,
            "source_date": date,
            "reason": None if value is not None else "fixture_missing",
        }
        for field, value in context.items()
        if field not in {"opportunity_state", "risk_state", "market_phase", "macro_state", "policy_mode"}
    }


def _row(
    date: str,
    *,
    candidate: str,
    opportunity_state: str,
    risk_state: str,
    market_phase: str,
    outcome: str,
    macro_score: float = 62,
    credit_score: float = 58,
    economy_score: float = 56,
    m1_m2: float = 0,
    pmi: float = 51,
    trend: float = 55,
    breadth: float = 45,
    liquidity: float = 45,
    crowding: float = 35,
    extension: float = 45,
) -> dict[str, object]:
    context = {
        "opportunity_state": opportunity_state,
        "risk_state": risk_state,
        "market_phase": market_phase,
        "policy_mode": "participate_with_control",
        "macro_state": "RECOVERY",
        "macro_score": macro_score,
        "macro_confidence": 0.75,
        "credit_score": credit_score,
        "economy_score": economy_score,
        "M1_M2_spread": m1_m2,
        "PMI": pmi,
        "trend_score": trend,
        "breadth_score": breadth,
        "liquidity_score": liquidity,
        "crowding_score": crowding,
        "price_extension_proxy": extension,
    }
    return {
        "date": date,
        "candidate": candidate,
        "outcome": outcome,
        "analysis_context": context,
        "future_label": {
            "future_window_complete": True,
            "failure": outcome == "failure",
            "missed_opportunity": outcome == "missed_opportunity",
        },
        "source_trace": _source_trace(date, context),
    }


def test_context_state_classifier_fixture() -> None:
    recovery = _row(
        "20240105",
        candidate="BALANCED_NEUTRAL",
        opportunity_state="EARLY_RECOVERY",
        risk_state="NORMAL",
        market_phase="EARLY_CYCLE",
        outcome="neutral",
    )
    structural = _row(
        "20240205",
        candidate="BALANCED_OPPORTUNITY",
        opportunity_state="STRUCTURAL_ROTATION",
        risk_state="CROWDED",
        market_phase="ROTATION",
        outcome="missed_opportunity",
        breadth=30,
        liquidity=34,
        extension=68,
    )
    risk = _row(
        "20240305",
        candidate="BALANCED_RISK",
        opportunity_state="EARLY_RECOVERY",
        risk_state="CROWDED",
        market_phase="LATE_CYCLE",
        outcome="failure",
        m1_m2=-5,
        extension=70,
    )
    assert classify_context_state(recovery)[0] == "BALANCED_RECOVERY"
    assert classify_context_state(structural)[0] == "BALANCED_STRUCTURAL_OPPORTUNITY"
    assert classify_context_state(risk)[0] == "BALANCED_RISK"


def test_exposure_context_state_audit_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_json(
            root / "macro_enhanced_context_analysis.json",
            {
                "metadata": {"engine": "V5.8 fixture", "as_of": "20260707"},
                "rows": [
                    _row("20240105", candidate="BALANCED_NEUTRAL", opportunity_state="EARLY_RECOVERY", risk_state="NORMAL", market_phase="EARLY_CYCLE", outcome="neutral"),
                    _row("20240205", candidate="BALANCED_OPPORTUNITY", opportunity_state="STRUCTURAL_ROTATION", risk_state="CROWDED", market_phase="ROTATION", outcome="missed_opportunity", breadth=30, liquidity=34, extension=68),
                    _row("20240305", candidate="BALANCED_RISK", opportunity_state="EARLY_RECOVERY", risk_state="CROWDED", market_phase="LATE_CYCLE", outcome="failure", m1_m2=-5, extension=70),
                    _row("20240405", candidate="BALANCED_NEUTRAL", opportunity_state="BULL_EXPANSION", risk_state="NORMAL", market_phase="EXPANSION", outcome="neutral", macro_score=50, credit_score=50, economy_score=48),
                ],
            },
        )

        payload = build_exposure_context_state_audit(root)

    assert payload["metadata"]["engine"] == "V5.9 Exposure Context State Model Design Audit"
    assert payload["summary"]["balanced_usable_rows"] == 4
    assert payload["summary"]["time_safety"]["violation_count"] == 0
    assert payload["summary"]["ready_for_mapper_change"] is False
    assert payload["context_state_quality"]["BALANCED_RECOVERY"]["sample_count"] == 1
    assert payload["context_state_quality"]["BALANCED_STRUCTURAL_OPPORTUNITY"]["future_opportunity_rate"] == 1.0
    assert payload["context_state_quality"]["BALANCED_RISK"]["future_risk_rate"] == 1.0
    assert payload["constraints"]["does_not_add_formal_state"] is True
    assert payload["constraints"]["no_trade_signal"] is True


def test_exposure_context_state_audit_real_payload() -> None:
    payload = build_exposure_context_state_audit()
    assert payload["summary"]["balanced_usable_rows"] >= 100
    assert payload["summary"]["time_safety"]["violation_count"] == 0
    assert payload["summary"]["ready_for_mapper_change"] is False
    assert payload["data_quality"]["future_label_not_used_for_state_assignment"] is True
    assert payload["context_state_quality"]["BALANCED_RISK"]["sample_count"] >= 1
    assert payload["constraints"]["research_candidates_only"] is True
    assert payload["constraints"]["no_etf_code"] is True


if __name__ == "__main__":
    test_context_state_classifier_fixture()
    test_exposure_context_state_audit_fixture()
    test_exposure_context_state_audit_real_payload()
    print("test_exposure_context_state_audit ok")
