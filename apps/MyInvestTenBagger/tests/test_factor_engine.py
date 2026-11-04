from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from tenbagger.factor_engine import FACTOR_COLUMNS, MODEL_V2_COLUMNS, FactorEngine


def _sample_task1_frame() -> pd.DataFrame:
    rows = []
    start = date(2024, 1, 1)
    for stock_idx, code in enumerate(["000001.SZ", "600519.SH", "300750.SZ"]):
        for day in range(260):
            current = start + timedelta(days=day)
            if current.weekday() >= 5:
                continue
            rows.append(
                {
                    "ts_code": code,
                    "date": current.isoformat(),
                    "open": 10 + stock_idx + day * 0.01,
                    "high": 10.5 + stock_idx + day * 0.01,
                    "low": 9.5 + stock_idx + day * 0.01,
                    "close": 10 + stock_idx * 2 + day * (0.02 + stock_idx * 0.005),
                    "revenue": 1000 + stock_idx * 200 + day,
                    "net_profit": 100 + stock_idx * 30 + day * 0.2,
                    "roe": 8 + stock_idx * 2,
                    "pe": 20 - stock_idx * 2,
                    "pb": 3 - stock_idx * 0.2,
                    "market_cap": 100000 + stock_idx * 10000,
                    "ann_date": "20231231",
                    "report_period": "20231231",
                }
            )
    return pd.DataFrame(rows)


def test_factor_engine_outputs_required_scores_without_nan() -> None:
    factors = FactorEngine().compute(_sample_task1_frame())

    assert set(FACTOR_COLUMNS).issubset(factors.columns)
    assert factors[FACTOR_COLUMNS].isna().sum().sum() == 0
    assert factors["tenbagger_score"].between(0, 100).all()
    assert factors["tenbagger_score"].std(ddof=0) > 0


def test_factor_engine_outputs_model_v2_scores_and_confidence() -> None:
    factors = FactorEngine().compute(_sample_task1_frame())

    assert set(MODEL_V2_COLUMNS).issubset(factors.columns)
    assert factors["tenbagger_score_v2"].between(0, 100).all()
    assert factors["v2_confidence_score"].between(0, 100).all()
    assert set(factors["v2_confidence_grade"].unique()).issubset({"A", "B", "C", "D"})
    assert factors["v2_fail_reasons"].notna().all()


def test_factor_validation_detects_no_future_leak_for_aligned_data() -> None:
    factors = FactorEngine().compute(_sample_task1_frame())
    validation = FactorEngine().validate(factors)

    assert validation.future_leak_rows == 0
    assert validation.nan_cells == 0


def test_cross_sectional_rank_direction() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-01"]),
            "metric": [1.0, 2.0, 3.0],
        }
    )
    engine = FactorEngine()

    high_is_good = engine._cross_sectional_rank(frame, "metric", higher_is_better=True)
    low_is_good = engine._cross_sectional_rank(frame, "metric", higher_is_better=False)

    assert high_is_good.iloc[2] == 100.0
    assert low_is_good.iloc[0] == 100.0
