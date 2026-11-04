# TASK 2 Result

TASK 2 implements the Factor Engine for the TenBagger system.

## Implemented

- `FactorEngine` with explicit methods:
  - `compute_value_factors()`
  - `compute_growth_factors()`
  - `compute_quality_factors()`
  - `compute_risk_factors()`
- Cross-sectional percentile ranking by date.
- TenBagger score V1:
  - 0.30 growth
  - 0.25 industry placeholder
  - 0.25 quality
  - 0.15 valuation
  - 0.05 momentum
- Output columns:
  `ts_code`, `date`, `value_score`, `growth_score`, `quality_score`,
  `risk_score`, `tenbagger_score`.
- Factor parquet storage:
  - `data/factors/by_date/`
  - `data/factors/by_stock/`
- Validation for:
  - future leak rows
  - NaN score cells
  - non-flat score distribution
- Web dashboard support for factor validation and latest factor scores.
- Tests for factor output schema, score ranges, non-flat distribution, and
  future-leak validation.

## Validation Run

Command:

```powershell
python scripts/run_task2.py
```

Result:

```json
{
  "stock_count": 10,
  "row_count": 8390,
  "date_range": {
    "start": "2023-01-03",
    "end": "2026-06-24"
  },
  "latest_trading_date": "2026-06-24",
  "validation": {
    "future_leak_rows": 0,
    "nan_cells": 0,
    "score_std": 11.453550213143139,
    "score_min": 20.1667,
    "score_max": 84.3333
  }
}
```

Latest top scores:

```text
000001.SZ  tenbagger=82.83  growth=85.00  quality=73.33 value=95.00 risk=100.00 momentum=80.00
300750.SZ  tenbagger=73.33  growth=100.00 quality=76.67 value=20.00 risk=10.00  momentum=90.00
600000.SH  tenbagger=70.00  growth=75.00  quality=60.00 value=95.00 risk=80.00  momentum=30.00
600519.SH  tenbagger=65.42  growth=80.00  quality=90.00 value=30.00 risk=50.00  momentum=50.00
601318.SH  tenbagger=52.75  growth=60.00  quality=40.00 value=80.00 risk=30.00  momentum=20.00
```

Test command:

```powershell
python -m pytest -q
```

Result:

```text
7 passed
```
