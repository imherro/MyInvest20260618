from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_gradient_analysis import (
    build_exposure_gradient_analysis,
    _opportunity_bucket,
    _risk_bucket,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _trace(date: str, context: dict[str, object]) -> dict[str, object]:
    return {
        field: {
            "available": value is not None,
            "value": value,
            "source": "fixture",
            "source_date": date,
            "release_date": date,
            "effective_date": date,
        }
        for field, value in context.items()
        if isinstance(value, (int, float))
    }


def _row(
    date: str,
    *,
    context_state: str,
    outcome: str,
    opportunity_state: str = "EARLY_RECOVERY",
    risk_state: str = "NORMAL",
    macro: float = 65,
    credit: float = 60,
    economy: float = 55,
    trend: float = 55,
    breadth: float = 55,
    liquidity: float = 55,
    extension: float = 45,
    m1_m2: float = 0,
) -> dict[str, object]:
    context = {
        "opportunity_state": opportunity_state,
        "risk_state": risk_state,
        "macro_score": macro,
        "credit_score": credit,
        "economy_score": economy,
        "M1_M2_spread": m1_m2,
        "trend_score": trend,
        "breadth_score": breadth,
        "liquidity_score": liquidity,
        "volatility_score": 55,
        "crowding_score": 45,
        "price_extension_proxy": extension,
        "industry_breadth": 55,
        "theme_persistence": 55,
    }
    return {
        "date": date,
        "context_state": context_state,
        "source_candidate": "fixture",
        "outcome": outcome,
        "analysis_context": context,
        "future_label": {"future_window_complete": True},
        "source_trace": _trace(date, context),
    }


def test_gradient_bucket_helpers() -> None:
    assert _risk_bucket(66) == "high_risk"
    assert _risk_bucket(50) == "medium_risk"
    assert _risk_bucket(30) == "low_risk"
    assert _opportunity_bucket(66) == "high_opportunity"
    assert _opportunity_bucket(50) == "medium_opportunity"
    assert _opportunity_bucket(30) == "low_opportunity"


def test_exposure_gradient_analysis_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_json(
            root / "exposure_context_state_audit.json",
            {
                "metadata": {"engine": "V5.9 fixture", "as_of": "20260707"},
                "rows": [
                    _row("20240105", context_state="BALANCED_RISK", outcome="failure", risk_state="CROWDED", credit=35, breadth=25, liquidity=25, extension=85, m1_m2=-8),
                    _row("20240205", context_state="BALANCED_RISK", outcome="failure", risk_state="CROWDED", credit=38, breadth=30, liquidity=30, extension=82, m1_m2=-7),
                    _row("20240305", context_state="BALANCED_STRUCTURAL_OPPORTUNITY", outcome="missed_opportunity", opportunity_state="STRUCTURAL_ROTATION", macro=80, credit=75, economy=70, trend=75, liquidity=72),
                    _row("20240405", context_state="BALANCED_NEUTRAL", outcome="neutral", macro=55, credit=55, economy=52, trend=50, breadth=50, liquidity=50),
                ],
            },
        )

        payload = build_exposure_gradient_analysis(root)

    assert payload["metadata"]["engine"] == "V5.10 Exposure Context Risk Gradient Analysis"
    assert payload["summary"]["balanced_usable_rows"] == 4
    assert payload["summary"]["time_safety"]["violation_count"] == 0
    assert payload["risk_bucket_analysis"]["high_risk"]["sample_count"] >= 2
    assert payload["opportunity_bucket_analysis"]["high_opportunity"]["sample_count"] >= 1
    assert payload["data_quality"]["no_parameter_optimization"] is True
    assert payload["constraints"]["does_not_modify_mapper"] is True
    assert payload["constraints"]["no_trade_signal"] is True


def test_exposure_gradient_analysis_real_payload() -> None:
    payload = build_exposure_gradient_analysis()
    assert payload["summary"]["balanced_usable_rows"] >= 100
    assert payload["summary"]["time_safety"]["violation_count"] == 0
    assert payload["summary"]["score_coverage"]["risk_gradient_score"]["available_count"] > 0
    assert payload["summary"]["score_coverage"]["opportunity_gradient_score"]["available_count"] > 0
    assert payload["data_quality"]["future_label_not_used_for_gradient"] is True
    assert payload["constraints"]["no_etf_code"] is True


if __name__ == "__main__":
    test_gradient_bucket_helpers()
    test_exposure_gradient_analysis_fixture()
    test_exposure_gradient_analysis_real_payload()
    print("test_exposure_gradient_analysis ok")
