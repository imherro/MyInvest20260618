from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.opportunity_risk_classifier import (
    build_opportunity_risk_snapshot,
    classify_opportunity_risk,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_classifier_separates_opportunity_and_risk() -> None:
    low_risk = classify_opportunity_risk(
        {
            "macro": {"state": "RECOVERY"},
            "structural": {"state": "BROAD_BULL"},
            "market_structure": {"state": "BULL_BROADENING", "index_trend": 80, "breadth": 60, "liquidity": 70},
            "industry_opportunity": {"theme_persistence": 72, "industry_breadth": 0.5, "top_industry_ratio": 0.12},
            "theme_risk": {"level": "low", "crowding_score": 30, "price_extension": 40, "warnings": []},
        }
    )
    assert low_risk.opportunity_state == "BULL_EXPANSION"
    assert low_risk.risk_state == "LOW_RISK"

    crowded = classify_opportunity_risk(
        {
            "macro": {"state": "RECOVERY"},
            "structural": {"state": "STRUCTURAL_BULL_ROTATION"},
            "market_structure": {"state": "BULL_DIVERGENCE", "index_trend": 80, "breadth": 15, "liquidity": 45},
            "industry_opportunity": {"theme_persistence": 82, "industry_breadth": 0.08, "top_industry_ratio": 0.3},
            "theme_risk": {"level": "medium", "crowding_score": 60, "price_extension": 75, "warnings": []},
        }
    )
    assert crowded.opportunity_state in {"STRUCTURAL_ROTATION", "LATE_BULL"}
    assert crowded.risk_state == "CROWDED"
    assert "theme_persistence_high" in crowded.evidence
    assert "industry_breadth_narrow" in crowded.evidence


def test_snapshot_with_minimal_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_json(
            root / "macro_cycle_snapshot.json",
            {"macro_state": "RECOVERY", "macro_score": 60, "confidence": 0.7},
        )
        _write_json(
            root / "structural_bull_snapshot.json",
            {
                "structural_state": "STRUCTURAL_BULL_ROTATION",
                "score": 70,
                "confidence": 0.8,
                "evidence": {
                    "market_structure": {"state": "BULL_DIVERGENCE", "index_trend": 80, "breadth": 15, "liquidity": 45},
                    "industry_opportunity": {
                        "theme_persistence": 80,
                        "industry_breadth": 0.1,
                        "top_industry_ratio": 0.28,
                    },
                },
            },
        )
        _write_json(
            root / "theme_risk_snapshot.json",
            {"theme_risk_level": "medium", "quality_score": 60, "crowding_score": 58, "warnings": []},
        )
        _write_json(
            root / "style_allocation_snapshot.json",
            {
                "metadata": {"as_of": "20240102"},
                "inputs": {
                    "as_of": "20240102",
                    "macro": {"state": "RECOVERY"},
                    "structural": {"state": "STRUCTURAL_BULL_ROTATION"},
                    "market_structure": {"state": "BULL_DIVERGENCE", "index_trend": 80, "breadth": 15, "liquidity": 45},
                    "industry_opportunity": {
                        "theme_persistence": 80,
                        "industry_breadth": 0.1,
                        "top_industry_ratio": 0.28,
                    },
                    "theme_risk": {"level": "medium", "crowding_score": 58, "warnings": []},
                    "generated_sources": {},
                },
                "preference": {"dominant_style": "growth"},
            },
        )
        _write_json(root / "style_incremental_analysis.json", {"summary": {"edge_read": {}}})
        _write_json(
            root / "v2_full_cycle_backtest.json",
            {
                "signals": {
                    "v2_structural_refined": [
                        {
                            "date": "20240102",
                            "as_of": "20240102",
                            "macro_state": "RECOVERY",
                            "structural_state": "STRUCTURAL_BULL_ROTATION",
                            "market_structure_state": "BULL_DIVERGENCE",
                            "theme_risk_level": "medium",
                        }
                    ]
                }
            },
        )
        _write_json(
            root / "historical_style_context.json",
            {
                "rows": [
                    {
                        "date": "20240102",
                        "style_context": {
                            "theme_persistence": 80,
                            "industry_breadth": 0.1,
                            "top_industry_ratio": 0.28,
                            "crowding_score": 58,
                            "price_extension": 72,
                            "trend": 0.8,
                            "breadth": 0.15,
                            "liquidity": 0.45,
                            "theme_risk_level": "medium",
                        },
                        "future_safe": True,
                        "data_quality": {"structural_features_available": True, "missing_fields": []},
                    }
                ]
            },
        )
        payload = build_opportunity_risk_snapshot(root, start_date="20240101", end_date="20240131")

    assert payload["metadata"]["engine"] == "V4.3 Market Opportunity vs Risk State Separation Engine"
    assert payload["current"]["opportunity_state"] in {"STRUCTURAL_ROTATION", "LATE_BULL"}
    assert payload["current"]["risk_state"] == "CROWDED"
    assert payload["historical_summary"]["replay_count"] == 1
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["does_not_modify_v4_1_policy"] is True


def test_snapshot_real_payload() -> None:
    payload = build_opportunity_risk_snapshot(start_date="20150101", end_date="20261231")
    assert payload["historical_summary"]["replay_count"] >= 100
    assert payload["constraints"]["state_separation_only"] is True
    assert payload["constraints"]["no_allocation"] is True
    assert payload["current"]["combined_state"]


if __name__ == "__main__":
    test_classifier_separates_opportunity_and_risk()
    test_snapshot_with_minimal_fixture()
    test_snapshot_real_payload()
    print("test_opportunity_risk_state ok")
