from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from structural_bull.structural_bull_classifier import classify_structural_bull
from structural_bull.structural_bull_engine import build_structural_bull_snapshot


def test_classifies_structural_bull_rotation() -> None:
    payload = {
        "macro": {"state": "RECOVERY", "score": 70, "confidence": 0.75, "as_of": "20260708"},
        "market_structure": {"state": "BULL_DIVERGENCE", "score": 54, "confidence": 0.70, "breadth": 15, "as_of": "20260707"},
        "industry_opportunity": {
            "source_type": "industry_index",
            "industry_strength": 56,
            "theme_persistence": 82,
            "rotation_health": 54,
            "industry_breadth": 0.10,
            "top_industry_ratio": 0.25,
            "as_of": "20260707",
        },
    }
    assert classify_structural_bull(payload) == "STRUCTURAL_BULL_ROTATION"


def test_structural_snapshot_has_no_allocation_outputs() -> None:
    macro = {"engine": "test macro", "macro_state": "RECOVERY", "macro_score": 70, "confidence": 0.75, "as_of": "20260708"}
    structure = {
        "engine": "test structure",
        "structure_state": "BULL_DIVERGENCE",
        "structure_score": 54,
        "confidence": 0.70,
        "as_of": "20260707",
        "metrics": {"breadth": 15, "index_trend": 78, "liquidity": 45},
    }
    industry = {
        "engine": "test industry",
        "industry_opportunity_score": 65,
        "industry_strength": 56,
        "theme_persistence": 82,
        "source_type": "industry_index",
        "as_of": "20260707",
        "metrics": {"rotation_health": 54, "industry_breadth": 0.10, "top_industry_ratio": 0.25},
        "top_themes": [{"name": "电子"}],
    }
    snapshot = build_structural_bull_snapshot("20260708", macro_payload=macro, structure_payload=structure, industry_payload=industry)
    assert snapshot["structural_state"] == "STRUCTURAL_BULL_ROTATION"
    assert snapshot["constraints"]["no_etf_allocation"] is True
    assert "allocation" not in snapshot
    assert "trade_signal" not in snapshot


def main() -> None:
    test_classifies_structural_bull_rotation()
    test_structural_snapshot_has_no_allocation_outputs()


if __name__ == "__main__":
    main()
