from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_numeric_context import (
    NUMERIC_FIELDS,
    build_exposure_numeric_context,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_numeric_context_is_time_safe_and_null_for_missing() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_json(
            root / "exposure_simulation.json",
            {
                "metadata": {"engine": "fixture-exposure", "as_of": "20240201"},
                "historical_replay": [
                    {
                        "date": "20240110",
                        "policy_mode": "participate_with_control",
                        "opportunity_state": "STRUCTURAL_ROTATION",
                        "risk_state": "NORMAL",
                        "market_phase": "EXPANSION",
                        "exposure_level": "BALANCED",
                        "exposure_band": "balanced_with_controls",
                        "future_window_complete": True,
                        "future_flags": {"strong_opportunity_event": True},
                    },
                    {
                        "date": "20240201",
                        "policy_mode": "protect_capital",
                        "opportunity_state": "DEFENSIVE_REPAIR",
                        "risk_state": "HIGH_RISK",
                        "market_phase": "CONTRACTION",
                        "exposure_level": "LOW",
                        "exposure_band": "risk_control",
                        "future_window_complete": True,
                        "future_flags": {"high_risk_event": True, "future_drawdown_gt_15": True},
                    },
                ],
            },
        )
        _write_json(
            root / "opportunity_risk_snapshot.json",
            {
                "historical_replay": [
                    {
                        "date": "20240105",
                        "metrics": {"trend": 62, "breadth": 48, "liquidity": 51, "pressure": 21},
                        "data_quality": {"context_date": "20240105", "missing_fields": []},
                    },
                    {
                        "date": "20240215",
                        "metrics": {"trend": 99, "breadth": 99, "liquidity": 99, "pressure": 99},
                        "data_quality": {"context_date": "20240215", "missing_fields": []},
                    },
                ]
            },
        )
        _write_json(
            root / "historical_style_context.json",
            {
                "rows": [
                    {
                        "date": "20240105",
                        "style_context": {
                            "industry_breadth": 0.41,
                            "theme_persistence": 72,
                            "crowding_score": 44,
                            "price_extension": 38,
                            "volatility": 0.63,
                        },
                        "data_quality": {
                            "context_date": "20240105",
                            "industry_count": 31,
                            "valuation_item_count": 8,
                            "missing_fields": [],
                        },
                    }
                ]
            },
        )
        _write_json(
            root / "structural_hazard_dataset.json",
            [
                {
                    "date": "20240104",
                    "features": {
                        "trend": 0.5,
                        "breadth": 0.4,
                        "liquidity": 0.3,
                        "volatility": 0.2,
                        "pressure": 0.1,
                    },
                }
            ],
        )
        _write_json(
            root / "shadow_equity_curve.json",
            {"decisions": [{"date": "20240108", "risk_score": 0.37}]},
        )

        payload = build_exposure_numeric_context(root)

    assert payload["metadata"]["engine"] == "V5.6 Numeric Context Enrichment for Exposure Replay"
    assert payload["constraints"]["does_not_modify_mapper"] is True
    assert payload["constraints"]["no_etf_code"] is True
    assert payload["data_quality"]["missing_values_are_null"] is True
    assert payload["summary"]["time_safety"]["violation_count"] == 0
    first = payload["rows"][0]
    second = payload["rows"][1]
    assert set(NUMERIC_FIELDS).issubset(set(first["exposure_context"]))
    assert first["exposure_context"]["trend_score"] == 62.0
    assert first["exposure_context"]["volatility_score"] == 63.0
    assert first["exposure_context"]["risk_score"] == 37.0
    assert first["exposure_context"]["macro_score"] is None
    assert first["source_trace"]["trend_score"]["source_date"] == "20240105"
    assert first["future_label"]["missed_opportunity"] is True
    assert second["exposure_context"]["trend_score"] == 62.0
    assert second["source_trace"]["trend_score"]["source_date"] == "20240105"
    assert second["future_label"]["failure"] is True


def test_zero_from_missing_source_is_not_treated_as_value() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_json(
            root / "exposure_simulation.json",
            {
                "metadata": {"engine": "fixture-exposure", "as_of": "20240110"},
                "historical_replay": [{"date": "20240110", "exposure_level": "BALANCED"}],
            },
        )
        _write_json(
            root / "opportunity_risk_snapshot.json",
            {
                "historical_replay": [
                    {
                        "date": "20240110",
                        "metrics": {"trend": 0, "breadth": 0, "liquidity": 0, "pressure": 0},
                        "data_quality": {
                            "context_date": "20240110",
                            "missing_fields": ["trend", "breadth", "liquidity", "pressure"],
                        },
                    }
                ]
            },
        )
        _write_json(
            root / "historical_style_context.json",
            {
                "rows": [
                    {
                        "date": "20240110",
                        "style_context": {
                            "industry_breadth": 0,
                            "theme_persistence": 0,
                            "crowding_score": 0,
                            "price_extension": 0,
                            "volatility": 0,
                        },
                        "data_quality": {
                            "context_date": "20240110",
                            "industry_count": 0,
                            "valuation_item_count": 0,
                            "missing_fields": ["volatility"],
                        },
                    }
                ]
            },
        )
        _write_json(root / "structural_hazard_dataset.json", [])
        _write_json(root / "shadow_equity_curve.json", {"decisions": []})

        payload = build_exposure_numeric_context(root)

    row = payload["rows"][0]
    assert row["exposure_context"]["trend_score"] is None
    assert row["exposure_context"]["industry_breadth"] is None
    assert row["exposure_context"]["crowding_score"] is None
    assert row["data_quality"]["missing_numeric_fields"]


def test_real_payload_numeric_context() -> None:
    payload = build_exposure_numeric_context()
    assert payload["summary"]["row_count"] >= 100
    assert payload["summary"]["time_safety"]["feature_date_lte_signal_date"] is True
    assert payload["summary"]["field_coverage"]["trend_score"]["available_count"] > 0
    assert payload["summary"]["field_coverage"]["crowding_score"]["available_count"] > 0
    assert payload["summary"]["field_coverage"]["macro_score"]["available_count"] > 0
    assert payload["summary"]["missing_macro_history"] is False
    assert payload["summary"]["fully_populated_non_macro_rows"] > 0
    assert payload["constraints"]["no_trade_signal"] is True


if __name__ == "__main__":
    test_numeric_context_is_time_safe_and_null_for_missing()
    test_zero_from_missing_source_is_not_treated_as_value()
    test_real_payload_numeric_context()
    print("test_exposure_numeric_context ok")
