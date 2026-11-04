from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.policy_historical_validation import build_policy_historical_validation


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_policy_validation_with_minimal_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
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
                        },
                        {
                            "date": "20240201",
                            "as_of": "20240201",
                            "macro_state": "RECOVERY",
                            "structural_state": "WEAK_MARKET",
                            "market_structure_state": "BEAR_RALLY",
                            "theme_risk_level": "high",
                        },
                    ]
                },
                "equity_curve": [
                    {"date": "20240103", "buy_hold_equal_equity": 1.0},
                    {"date": "20240131", "buy_hold_equal_equity": 0.88},
                    {"date": "20240202", "buy_hold_equal_equity": 0.89},
                    {"date": "20240229", "buy_hold_equal_equity": 0.95},
                ],
                "period_attribution": {},
            },
        )
        _write_json(
            root / "historical_style_context.json",
            {
                "rows": [
                    {
                        "date": "20240102",
                        "style_context": {
                            "industry_breadth": 0.1,
                            "positive_industry_ratio": 0.2,
                            "top_industry_ratio": 0.3,
                            "theme_persistence": 80,
                            "crowding_score": 60,
                            "price_extension": 75,
                            "theme_risk_level": "medium",
                            "trend": 0.7,
                            "breadth": 0.15,
                            "liquidity": 0.45,
                            "pressure": 0.2,
                        },
                        "top_themes": [],
                        "future_safe": True,
                        "data_quality": {
                            "structural_features_available": True,
                            "missing_fields": [],
                        },
                    }
                ]
            },
        )
        _write_json(
            root / "style_incremental_analysis.json",
            {"summary": {"edge_read": {"style_incremental_edge_status": "weak_short_horizon_trace"}}},
        )
        payload = build_policy_historical_validation(root, start_date="20240101", end_date="20240301")

    assert payload["metadata"]["engine"] == "V4.2 Risk Budget Historical Validation"
    assert payload["summary"]["replay_count"] == 2
    assert payload["constraints"]["fixed_v4_1_policy_rules"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_etf_code"] is True
    assert payload["data_quality"]["uses_future_returns_only_for_validation_labels"] is True
    assert "historical_replay" in payload
    assert payload["historical_replay"][0]["risk_constraints"]["style_score_may_not_expand_budget_by_itself"] is True
    assert payload["policy_contradiction_audit"]["contradiction_count"] >= 0


def test_policy_validation_real_payload() -> None:
    payload = build_policy_historical_validation(start_date="20150101", end_date="20261231")
    assert payload["summary"]["replay_count"] >= 100
    assert payload["constraints"]["no_position_sizing"] is True
    assert payload["constraints"]["not_a_return_optimization_backtest"] is True
    assert payload["period_validation"]
    assert payload["summary"]["context_coverage"]["complete_structural_context_share"] >= 0


if __name__ == "__main__":
    test_policy_validation_with_minimal_fixture()
    test_policy_validation_real_payload()
    print("test_policy_validation ok")
