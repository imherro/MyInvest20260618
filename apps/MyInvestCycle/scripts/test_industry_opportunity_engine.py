from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from industry_structure.industry_loader import IndustryAsset
from industry_structure.industry_strength_engine import build_industry_strength
from industry_structure.theme_persistence_engine import build_theme_persistence


def make_frame(code: str, daily_return: float, periods: int = 120) -> pd.DataFrame:
    close = 1000.0
    rows = []
    for date_text in pd.bdate_range("2026-01-02", periods=periods):
        close *= 1.0 + daily_return
        rows.append(
            {
                "ts_code": code,
                "trade_date": date_text.strftime("%Y%m%d"),
                "close": close,
                "open": close,
                "high": close,
                "low": close,
                "pre_close": close,
                "change": 0.0,
                "pct_chg": daily_return * 100.0,
                "vol": 1.0,
                "amount": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_strength_ranks_persistent_leader() -> None:
    assets = {
        "801001.SI": IndustryAsset("801001.SI", "强势行业", "industry_index", "test"),
        "801002.SI": IndustryAsset("801002.SI", "中性行业", "industry_index", "test"),
        "801003.SI": IndustryAsset("801003.SI", "弱势行业", "industry_index", "test"),
    }
    frames = {
        "801001.SI": make_frame("801001.SI", 0.003),
        "801002.SI": make_frame("801002.SI", 0.001),
        "801003.SI": make_frame("801003.SI", -0.001),
    }
    benchmarks = {
        "000300.SH": make_frame("000300.SH", 0.0005),
        "000905.SH": make_frame("000905.SH", 0.0007),
    }
    strength = build_industry_strength(assets, frames, benchmarks, "20260618")
    assert strength["industries"][0]["code"] == "801001.SI"
    assert strength["industry_strength"] > 60


def test_theme_persistence_uses_trailing_ranks() -> None:
    assets = {
        "801001.SI": IndustryAsset("801001.SI", "强势行业", "industry_index", "test"),
        "801002.SI": IndustryAsset("801002.SI", "弱势行业", "industry_index", "test"),
    }
    frames = {
        "801001.SI": make_frame("801001.SI", 0.003),
        "801002.SI": make_frame("801002.SI", -0.001),
    }
    persistence = build_theme_persistence(assets, frames, "20260618")
    assert persistence["persistence_by_industry"][0]["code"] == "801001.SI"
    assert persistence["theme_persistence_score"] > 50


def main() -> None:
    test_strength_ranks_persistent_leader()
    test_theme_persistence_uses_trailing_ranks()


if __name__ == "__main__":
    main()
