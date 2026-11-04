from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.market_phase_classifier import build_market_phase_snapshot, classify_market_phase


def _row(**metrics):
    return {
        "opportunity_state": metrics.pop("opportunity_state", "EARLY_RECOVERY"),
        "risk_state": metrics.pop("risk_state", "NORMAL"),
        "metrics": {
            "macro_state": metrics.pop("macro_state", "RECOVERY"),
            "structural_state": metrics.pop("structural_state", "BROAD_BULL"),
            **metrics,
        },
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_phase_rule_examples() -> None:
    assert classify_market_phase(_row(trend=45, breadth=42, liquidity=55, crowding_score=35)).phase == "EARLY_CYCLE"
    assert (
        classify_market_phase(
            _row(trend=72, breadth=58, liquidity=62, industry_breadth=0.5, crowding_score=40)
        ).phase
        == "EXPANSION"
    )
    assert (
        classify_market_phase(
            _row(trend=58, breadth=25, liquidity=48, theme_persistence=76, industry_breadth=0.18)
        ).phase
        == "ROTATION"
    )
    assert (
        classify_market_phase(
            _row(trend=78, breadth=18, liquidity=45, theme_persistence=82, crowding_score=62, price_extension_proxy=75)
        ).phase
        == "LATE_CYCLE"
    )
    assert (
        classify_market_phase(
            _row(
                macro_state="CONTRACTION",
                structural_state="WEAK_MARKET",
                trend=28,
                breadth=20,
                liquidity=25,
                risk_state="HIGH_RISK",
            )
        ).phase
        == "CONTRACTION"
    )


def test_market_phase_snapshot_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        rows = [
            {"date": "20240101", **_row(trend=45, breadth=42, liquidity=55, crowding_score=35)},
            {
                "date": "20240201",
                **_row(trend=78, breadth=18, liquidity=45, theme_persistence=82, crowding_score=62, price_extension_proxy=75),
            },
            {
                "date": "20240301",
                **_row(
                    macro_state="CONTRACTION",
                    structural_state="WEAK_MARKET",
                    trend=28,
                    breadth=20,
                    liquidity=25,
                    risk_state="HIGH_RISK",
                ),
            },
        ]
        _write_json(
            root / "opportunity_risk_snapshot.json",
            {
                "metadata": {"engine": "fixture", "as_of": "20240301"},
                "current": rows[-1],
                "historical_replay": rows,
            },
        )
        _write_json(
            root / "policy_effectiveness.json",
            {
                "summary": {"policy_usefulness": {"structural_high_risk_rate_spread": 0.1}},
                "validation_rows": [
                    {
                        "date": "20240101",
                        "future_window_complete": True,
                        "future_flags": {"high_risk_event": False, "strong_opportunity_event": True},
                        "future_environment": "strong_uptrend",
                    },
                    {
                        "date": "20240201",
                        "future_window_complete": True,
                        "future_flags": {"high_risk_event": True, "strong_opportunity_event": False},
                        "future_environment": "drawdown_stress",
                    },
                ],
            },
        )
        payload = build_market_phase_snapshot(root)

    assert payload["metadata"]["engine"] == "V4.6 Market Phase Classification Layer"
    assert payload["current"]["phase"] == "CONTRACTION"
    assert payload["historical_summary"]["replay_count"] == 3
    assert payload["historical_summary"]["future_validation"]["usable_rows"] == 2
    assert payload["constraints"]["no_trade_signal"] is True


def test_market_phase_real_payload() -> None:
    payload = build_market_phase_snapshot()
    assert payload["historical_summary"]["replay_count"] >= 100
    assert payload["current"]["phase"] in {"EARLY_CYCLE", "EXPANSION", "ROTATION", "LATE_CYCLE", "CONTRACTION", "UNKNOWN"}
    assert payload["data_quality"]["classification_no_future_returns"] is True
    assert payload["constraints"]["does_not_modify_v4_4_policy_mapping"] is True


if __name__ == "__main__":
    test_phase_rule_examples()
    test_market_phase_snapshot_fixture()
    test_market_phase_real_payload()
    print("test_market_phase_classifier ok")
