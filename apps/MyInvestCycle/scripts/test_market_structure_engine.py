from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from market_structure.structure_classifier import classify_structure
from market_structure.structure_score_engine import score_index_trend


def make_index_frame(direction: float = 1.0) -> pd.DataFrame:
    rows = []
    close = 1000.0
    for i, trade_date in enumerate(pd.bdate_range("2025-01-02", periods=280)):
        close *= 1.0 + direction * 0.0008
        rows.append(
            {
                "ts_code": "000001.SH",
                "trade_date": trade_date.strftime("%Y%m%d"),
                "close": close,
                "open": close,
                "high": close,
                "low": close,
                "pre_close": close,
                "change": 0.0,
                "pct_chg": direction * 0.08,
                "vol": 1.0,
                "amount": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_score_index_trend_has_no_future_requirement() -> None:
    metrics = score_index_trend(make_index_frame(1.0))
    assert metrics["trend_score"] > 60
    assert metrics["above_ma250"] is True


def test_classify_bull_divergence() -> None:
    state = classify_structure(
        {
            "index_trend": 75,
            "breadth": 35,
            "liquidity": 50,
            "pullback_health": 80,
            "structure_score": 60,
        }
    )
    assert state == "BULL_DIVERGENCE"


def test_classify_structural_bull_requires_industry_data() -> None:
    without_industry = classify_structure(
        {
            "index_trend": 55,
            "breadth": 45,
            "liquidity": 50,
            "pullback_health": 65,
            "structure_score": 55,
        }
    )
    with_industry = classify_structure(
        {
            "index_trend": 55,
            "breadth": 45,
            "liquidity": 50,
            "pullback_health": 65,
            "industry_strength": 82,
            "theme_persistence": 70,
            "structure_score": 70,
        }
    )
    assert without_industry != "STRUCTURAL_BULL_ROTATION"
    assert with_industry == "STRUCTURAL_BULL_ROTATION"


def main() -> None:
    test_score_index_trend_has_no_future_requirement()
    test_classify_bull_divergence()
    test_classify_structural_bull_requires_industry_data()


if __name__ == "__main__":
    main()
