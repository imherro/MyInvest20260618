from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from tenbagger.alpha_validation import AlphaValidator
from tenbagger.factor_engine import FactorEngine
from tenbagger.screener import HardFilter, HardFilterConfig


def _frame() -> pd.DataFrame:
    rows = []
    start = date(2024, 1, 1)
    for idx, code in enumerate(["A", "B", "C", "D"]):
        for day in range(180):
            current = start + timedelta(days=day)
            if current.weekday() >= 5:
                continue
            rows.append(
                {
                    "ts_code": code,
                    "date": current.isoformat(),
                    "close": 10 + idx + day * (0.03 + idx * 0.01),
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "revenue": 100 + idx * 20 + day,
                    "net_profit": 10 + idx * 3 + day * 0.2,
                    "roe": 1 + idx,
                    "pe": 10 + idx,
                    "pb": 1 + idx * 0.2,
                    "market_cap": 100 + idx,
                    "industry": "tech" if idx < 2 else "health",
                    "ann_date": "20231231",
                    "report_period": "20231231",
                    "debt_ratio": 0.3,
                }
            )
    return pd.DataFrame(rows)


def test_hard_filter_marks_candidates_and_reasons() -> None:
    factors = FactorEngine().compute(_frame())
    filtered = HardFilter(
        HardFilterConfig(
            max_market_cap=999,
            min_revenue_growth=-1,
            min_roe=0,
            max_debt_ratio=0.9,
        )
    ).apply_filters(factors)

    assert filtered["is_candidate"].any()
    assert "fail_reasons" in filtered.columns


def test_alpha_validator_outputs_ic_and_preview() -> None:
    task1 = _frame()
    factors = FactorEngine().compute(task1)
    validator = AlphaValidator(horizons=(21,))
    enriched = validator.attach_forward_returns(factors, task1)
    summary = validator.ic_summary(enriched)
    preview = validator.backtest_preview(enriched, horizon=21)

    assert "tenbagger_score_21d" in summary
    assert preview.observations > 0
