from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.macro_enhanced_context_analysis import build_macro_enhanced_context_analysis


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _numeric_row(
    date: str,
    opportunity_state: str,
    risk_state: str,
    market_phase: str,
    *,
    failure: bool = False,
    missed: bool = False,
    trend: float = 55,
    breadth: float = 55,
    liquidity: float = 55,
    crowding: float = 45,
) -> dict[str, object]:
    context = {
        "exposure_level": "BALANCED",
        "policy_mode": "participate_with_control",
        "opportunity_state": opportunity_state,
        "risk_state": risk_state,
        "market_phase": market_phase,
        "trend_score": trend,
        "breadth_score": breadth,
        "liquidity_score": liquidity,
        "volatility_score": 50,
        "industry_breadth": 55,
        "theme_persistence": 50,
        "crowding_score": crowding,
        "price_extension_proxy": crowding,
    }
    trace = {
        field: {"available": True, "value": value, "source_date": date, "source": "fixture"}
        for field, value in context.items()
        if isinstance(value, (int, float))
    }
    return {
        "date": date,
        "exposure_context": context,
        "future_label": {
            "future_window_complete": True,
            "failure": failure,
            "missed_opportunity": missed,
            "future_environment": "fixture",
        },
        "source_trace": trace,
    }


def _macro_row(
    date: str,
    *,
    macro_score: float,
    credit_score: float,
    pmi: float,
    m1_m2: float,
    release_date: str | None = None,
) -> dict[str, object]:
    values = {
        "macro_score": macro_score,
        "macro_confidence": 0.8,
        "credit_score": credit_score,
        "economy_score": 55,
        "external_score": 60,
        "M1_growth": 2,
        "M2_growth": 8,
        "M1_M2_spread": m1_m2,
        "social_financing_growth": 8,
        "SHIBOR": 2.1,
        "US10Y": 4.0,
        "PMI": pmi,
        "CPI": 1.5,
        "PPI": -1.0,
    }
    trace_date = release_date or date
    return {
        "date": date,
        "macro_context": {"macro_state": "RECOVERY", **values},
        "source_trace": {
            field: {
                "available": True,
                "value": value,
                "release_date": trace_date,
                "effective_date": trace_date,
                "source": "fixture",
            }
            for field, value in values.items()
        }
        | {
            "macro_state": {
                "available": True,
                "value": "RECOVERY",
                "release_date": trace_date,
                "effective_date": trace_date,
                "source": "fixture",
            }
        },
    }


def test_macro_enhanced_context_analysis_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        risk_context = {
            "opportunity_state": "EARLY_RECOVERY",
            "risk_state": "NORMAL",
            "market_phase": "EARLY_CYCLE",
            "usable_rows": 3,
            "failure_rate": 0.666667,
            "missed_opportunity_rate": 0,
        }
        opportunity_context = {
            "opportunity_state": "STRUCTURAL_ROTATION",
            "risk_state": "NORMAL",
            "market_phase": "ROTATION",
            "usable_rows": 3,
            "failure_rate": 0,
            "missed_opportunity_rate": 0.333333,
        }
        _write_json(
            root / "exposure_context_analysis.json",
            {"context_comparison": [risk_context, opportunity_context]},
        )
        _write_json(
            root / "balanced_context_audit.json",
            {
                "metadata": {"engine": "V5.4 fixture", "as_of": "20260707"},
                "summary": {"candidate_quality": {"status": "candidate_not_ready_for_mapper_change"}},
            },
        )
        _write_json(
            root / "exposure_numeric_context.json",
            {
                "metadata": {"engine": "V5.6 fixture", "as_of": "20260707"},
                "rows": [
                    _numeric_row("20240105", "EARLY_RECOVERY", "NORMAL", "EARLY_CYCLE", failure=True, breadth=25, liquidity=30),
                    _numeric_row("20240205", "EARLY_RECOVERY", "NORMAL", "EARLY_CYCLE", failure=True, breadth=28, liquidity=35),
                    _numeric_row("20240305", "EARLY_RECOVERY", "NORMAL", "EARLY_CYCLE", trend=42, breadth=36, liquidity=38),
                    _numeric_row("20240405", "STRUCTURAL_ROTATION", "NORMAL", "ROTATION", missed=True, trend=62, breadth=64, liquidity=66),
                    _numeric_row("20240505", "STRUCTURAL_ROTATION", "NORMAL", "ROTATION", missed=True, trend=60, breadth=61, liquidity=63),
                    _numeric_row("20240605", "STRUCTURAL_ROTATION", "NORMAL", "ROTATION", trend=58, breadth=59, liquidity=61),
                ],
            },
        )
        _write_json(
            root / "macro_context_history.json",
            {
                "rows": [
                    _macro_row("20240105", macro_score=44, credit_score=42, pmi=49, m1_m2=-5),
                    _macro_row("20240205", macro_score=45, credit_score=41, pmi=48, m1_m2=-6),
                    _macro_row("20240305", macro_score=48, credit_score=43, pmi=49, m1_m2=-4),
                    _macro_row("20240405", macro_score=62, credit_score=58, pmi=51, m1_m2=1),
                    _macro_row("20240505", macro_score=64, credit_score=60, pmi=52, m1_m2=2),
                    _macro_row("20240605", macro_score=66, credit_score=61, pmi=52, m1_m2=1),
                ]
            },
        )

        payload = build_macro_enhanced_context_analysis(root)

    assert payload["metadata"]["engine"] == "V5.8 Macro-Enhanced Exposure Context Re-Attribution"
    assert payload["summary"]["balanced_usable_rows"] == 6
    assert payload["summary"]["time_safety"]["violation_count"] == 0
    assert payload["candidate_re_attribution"]["BALANCED_RISK"]["sample_count"] == 3
    assert payload["candidate_re_attribution"]["BALANCED_RISK"]["drivers"]["macro_credit_weak"] is True
    assert payload["candidate_re_attribution"]["BALANCED_RISK"]["drivers"]["breadth_low"] is True
    assert payload["candidate_re_attribution"]["BALANCED_OPPORTUNITY"]["drivers"]["macro_recovery"] is True
    assert payload["candidate_re_attribution"]["BALANCED_OPPORTUNITY"]["drivers"]["structural_rotation"] is True
    assert payload["constraints"]["does_not_modify_mapper"] is True
    assert payload["constraints"]["no_trade_signal"] is True


def test_macro_enhanced_context_blocks_future_macro_trace() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_json(
            root / "exposure_context_analysis.json",
            {
                "context_comparison": [
                    {
                        "opportunity_state": "EARLY_RECOVERY",
                        "risk_state": "NORMAL",
                        "market_phase": "EARLY_CYCLE",
                        "usable_rows": 3,
                        "failure_rate": 0.666667,
                    }
                ]
            },
        )
        _write_json(root / "balanced_context_audit.json", {"metadata": {"as_of": "20260707"}})
        _write_json(
            root / "exposure_numeric_context.json",
            {
                "metadata": {"engine": "V5.6 fixture", "as_of": "20260707"},
                "rows": [
                    _numeric_row("20240105", "EARLY_RECOVERY", "NORMAL", "EARLY_CYCLE", failure=True),
                ],
            },
        )
        _write_json(
            root / "macro_context_history.json",
            {
                "rows": [
                    _macro_row("20240105", macro_score=60, credit_score=60, pmi=51, m1_m2=1, release_date="20240120"),
                ]
            },
        )

        payload = build_macro_enhanced_context_analysis(root)

    row = payload["rows"][0]
    assert row["analysis_context"]["macro_score"] is None
    assert row["source_trace"]["macro_score"]["reason"] == "no_time_safe_macro_context"
    assert payload["summary"]["time_safety"]["violation_count"] == 0
    assert payload["summary"]["time_safety"]["blocked_future_values"] > 0


def test_macro_enhanced_context_analysis_real_payload() -> None:
    payload = build_macro_enhanced_context_analysis()
    assert payload["summary"]["balanced_usable_rows"] >= 100
    assert payload["summary"]["time_safety"]["violation_count"] == 0
    assert payload["summary"]["field_coverage"]["macro_score"]["available_count"] > 0
    assert payload["candidate_re_attribution"]["BALANCED_RISK"]["sample_count"] >= 1
    assert payload["candidate_re_attribution"]["BALANCED_OPPORTUNITY"]["sample_count"] >= 1
    assert payload["data_quality"]["uses_fixed_v5_4_candidate_labels"] is True
    assert payload["constraints"]["no_etf_code"] is True
    assert payload["constraints"]["no_return_optimization"] is True


if __name__ == "__main__":
    test_macro_enhanced_context_analysis_fixture()
    test_macro_enhanced_context_blocks_future_macro_trace()
    test_macro_enhanced_context_analysis_real_payload()
    print("test_macro_enhanced_context_analysis ok")
