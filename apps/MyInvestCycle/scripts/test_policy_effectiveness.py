from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.policy_counterfactual import future_environment_flags, future_environment_label
from allocation_policy.policy_effectiveness import build_policy_effectiveness


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_index_cache(root: Path) -> None:
    path = root / "cache" / "index_daily_000001_SH.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount"]
    close = 100.0
    for idx in range(180):
        if idx < 70:
            close *= 1.001
        elif idx < 125:
            close *= 0.996
        else:
            close *= 1.002
        trade_date = f"2024{(idx // 22) + 1:02d}{(idx % 22) + 1:02d}"
        rows.append(f"000001.SH,{trade_date},{close:.4f},{close:.4f},{close:.4f},{close:.4f},{close:.4f},0,0,0,0")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_future_environment_labels() -> None:
    stress = {
        "future_window_complete": True,
        "forward_return_120d": -0.05,
        "max_drawdown_60d": -0.11,
        "max_drawdown_120d": -0.16,
        "realized_volatility_60d": 0.22,
    }
    assert future_environment_label(stress) == "drawdown_stress"
    assert future_environment_flags(stress)["future_drawdown_gt_15"] is True

    uptrend = {
        "future_window_complete": True,
        "forward_return_120d": 0.16,
        "max_drawdown_60d": -0.03,
        "max_drawdown_120d": -0.05,
        "realized_volatility_60d": 0.15,
    }
    assert future_environment_label(uptrend) == "strong_uptrend"
    assert future_environment_flags(uptrend)["strong_opportunity_event"] is True


def test_policy_effectiveness_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_index_cache(root)
        rows = [
            {
                "date": "20240101",
                "opportunity_state": "BULL_EXPANSION",
                "risk_state": "NORMAL",
                "combined_state": "BULL_EXPANSION__NORMAL",
                "policy_mode": "participate_selectively",
                "actions_allowed": [],
                "actions_blocked": [],
            },
            {
                "date": "20240201",
                "opportunity_state": "STRUCTURAL_ROTATION",
                "risk_state": "CROWDED",
                "combined_state": "STRUCTURAL_ROTATION__CROWDED",
                "policy_mode": "participate_with_control",
                "actions_allowed": [],
                "actions_blocked": [],
            },
        ]
        _write_json(
            root / "opportunity_risk_policy.json",
            {
                "metadata": {"engine": "fixture", "as_of": "20240701"},
                "historical_replay": rows,
            },
        )
        _write_json(root / "opportunity_risk_snapshot.json", {"metadata": {}, "historical_replay": []})
        _write_json(
            root / "v2_full_cycle_backtest.json",
            {
                "signals": {
                    "v2_structural_refined": [
                        {"date": "20240101", "structural_state": "BROAD_BULL"},
                        {"date": "20240201", "structural_state": "STRUCTURAL_BULL_ROTATION"},
                    ]
                }
            },
        )
        payload = build_policy_effectiveness(root, start_date="20240101", end_date="20240904")

    assert payload["metadata"]["engine"] == "V4.5 Policy Effectiveness Audit & Counterfactual Validation"
    assert payload["summary"]["replay_rows"] == 2
    assert payload["summary"]["usable_rows"] >= 1
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["data_quality"]["future_returns_used_only_for_validation_labels"] is True


def test_policy_effectiveness_real_payload() -> None:
    payload = build_policy_effectiveness(start_date="20150101", end_date="20261231")
    assert payload["summary"]["replay_rows"] >= 100
    assert payload["summary"]["usable_rows"] >= 100
    assert payload["summary"]["policy_usefulness"]["status"]
    assert payload["constraints"]["does_not_modify_v4_4_policy_mapping"] is True


if __name__ == "__main__":
    test_future_environment_labels()
    test_policy_effectiveness_fixture()
    test_policy_effectiveness_real_payload()
    print("test_policy_effectiveness ok")
