from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from theme_risk.crowding_risk_engine import evaluate_crowding_risk
from theme_risk.valuation_pressure_engine import evaluate_valuation_pressure


def make_frame(code: str, daily_return: float, periods: int = 260) -> pd.DataFrame:
    close = 1000.0
    rows = []
    for date_text in pd.bdate_range("2025-07-01", periods=periods):
        close *= 1.0 + daily_return
        rows.append({"ts_code": code, "trade_date": date_text.strftime("%Y%m%d"), "close": close})
    return pd.DataFrame(rows)


def test_valuation_pressure_flags_extended_theme() -> None:
    themes = [{"code": "801080.SI", "name": "电子", "composite_score": 90}]
    frames = {"801080.SI": make_frame("801080.SI", 0.003)}
    items = evaluate_valuation_pressure(themes, frames, "20260629")
    assert items[0]["valuation_pressure_score"] > 55
    assert "near_252d_high_position" in items[0]["warnings"]


def test_crowding_uses_concentration_and_breadth() -> None:
    industry = {
        "top_themes": [
            {"code": "A", "composite_score": 90},
            {"code": "B", "composite_score": 40},
            {"code": "C", "composite_score": 30},
        ],
        "metrics": {"industry_breadth": 0.08, "positive_industry_ratio": 0.25, "top_industry_ratio": 0.10},
    }
    crowding = evaluate_crowding_risk(industry, [{"valuation_pressure_score": 80}])
    assert crowding["crowding_score"] > 55
    assert "industry_breadth_narrow" in crowding["warnings"]


def main() -> None:
    test_valuation_pressure_flags_extended_theme()
    test_crowding_uses_concentration_and_breadth()


if __name__ == "__main__":
    main()
