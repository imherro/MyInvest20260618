from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_allocation.allocation_engine import build_allocation_intent_snapshot


def structural(state: str, macro: str = "BULL") -> dict[str, object]:
    return {
        "engine": "test structural",
        "structural_state": state,
        "as_of": "20260707",
        "evidence": {
            "macro": {"state": macro, "score": 80, "confidence": 0.8, "as_of": "20260708"},
            "market_structure": {"state": "BULL_BROADENING", "score": 75, "breadth": 65, "as_of": "20260707"},
            "industry_opportunity": {"score": 80, "industry_strength": 75, "theme_persistence": 82, "as_of": "20260707"},
        },
    }


def theme_risk(level: str) -> dict[str, object]:
    return {
        "engine": "test theme risk",
        "theme_risk_level": level,
        "quality_score": 75 if level == "low" else 45,
        "crowding_score": 25 if level == "low" else 80,
        "warnings": [],
        "as_of": "20260707",
    }


def test_bull_low_risk_is_offensive() -> None:
    snapshot = build_allocation_intent_snapshot(
        "20260708",
        structural_payload=structural("STRUCTURAL_BULL_ROTATION"),
        theme_risk_payload=theme_risk("low"),
    )
    assert snapshot["allocation_intent"]["risk_budget"] in {"medium_high", "high"}


def test_bull_high_risk_reduces_budget() -> None:
    snapshot = build_allocation_intent_snapshot(
        "20260708",
        structural_payload=structural("STRUCTURAL_BULL_ROTATION"),
        theme_risk_payload=theme_risk("high"),
    )
    assert snapshot["allocation_intent"]["risk_budget"] in {"low", "medium"}


def test_bear_structure_is_defensive() -> None:
    snapshot = build_allocation_intent_snapshot(
        "20260708",
        structural_payload=structural("BEAR_STRUCTURE", macro="BEAR"),
        theme_risk_payload=theme_risk("low"),
    )
    assert snapshot["allocation_intent"]["risk_budget"] == "defensive"


def test_no_etf_or_trade_outputs() -> None:
    snapshot = build_allocation_intent_snapshot(
        "20260708",
        structural_payload=structural("STRUCTURAL_BULL_ROTATION"),
        theme_risk_payload=theme_risk("low"),
    )
    text = str(snapshot)
    assert ".SH" not in text and ".SZ" not in text
    assert "trade_signal" not in snapshot
    assert "order" not in snapshot
    assert snapshot["constraints"]["no_etf_code"] is True


def main() -> None:
    test_bull_low_risk_is_offensive()
    test_bull_high_risk_reduces_budget()
    test_bear_structure_is_defensive()
    test_no_etf_or_trade_outputs()


if __name__ == "__main__":
    main()
