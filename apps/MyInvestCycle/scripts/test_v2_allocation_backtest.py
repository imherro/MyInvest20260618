from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.allocation_backtest_engine import run_v2_allocation_backtest


def _price_frame(code: str, dates: list[str], returns: list[float]) -> pd.DataFrame:
    close = 100.0
    rows = []
    for date, daily_return in zip(dates, returns):
        pre_close = close
        close = close * (1.0 + daily_return)
        rows.append(
            {
                "ts_code": code,
                "trade_date": date,
                "close": close,
                "pre_close": pre_close,
                "pct_chg": daily_return * 100.0,
            }
        )
    return pd.DataFrame(rows)


def _snapshot_builder(date_text: str) -> dict[str, object]:
    high_dates = {"20240102", "20240104"}
    risk_budget = "high" if date_text in high_dates else "defensive"
    return {
        "as_of": date_text,
        "structural_state": "STRUCTURAL_BULL_ROTATION" if risk_budget == "high" else "WEAK_MARKET",
        "allocation_intent": {
            "risk_budget": risk_budget,
            "style_preference": ["validation_proxy"],
        },
        "risk_adjustments": {
            "theme_risk_level": "low" if risk_budget == "high" else "high",
        },
        "evidence": {
            "macro": {"state": "RECOVERY"},
            "market_structure": {"state": "BULL_DIVERGENCE"},
        },
        "explanation": ["synthetic snapshot"],
    }


def test_v2_allocation_backtest_t_plus_1_and_boundaries() -> None:
    dates = ["20240102", "20240103", "20240104", "20240105", "20240108", "20240109"]
    price_history = {
        "510300.SH": _price_frame("510300.SH", dates, [0.00, 0.02, 0.01, -0.01, 0.00, 0.01]),
        "510500.SH": _price_frame("510500.SH", dates, [0.00, 0.01, 0.02, -0.01, 0.00, 0.02]),
        "511880.SH": _price_frame("511880.SH", dates, [0.00, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001]),
    }
    payload = run_v2_allocation_backtest(
        start_date="20240102",
        end_date="20240109",
        rebalance_every_sessions=2,
        price_history=price_history,
        snapshot_builder=_snapshot_builder,
        shadow_backtest_path=ROOT_DIR / "missing_shadow.json",
        m2_backtest_path=ROOT_DIR / "missing_m2.json",
    )
    assert payload["metadata"]["walk_forward"] is True
    assert payload["metadata"]["no_trade_execution"] is True
    assert payload["validation"]["walk_forward_t_plus_1"] is True
    assert payload["signals"][0]["date"] == "20240102"
    assert payload["daily_returns"][0]["date"] == "20240103"
    assert payload["daily_returns"][0]["target_exposure"] == 0.8
    assert payload["summary"]["rebalance_count"] >= 2
    assert "benchmark_510500_return" in payload["benchmark_comparison"]
    assert "structural_state" in payload["state_attribution"]


if __name__ == "__main__":
    test_v2_allocation_backtest_t_plus_1_and_boundaries()
    print("ok")
