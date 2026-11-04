# TASK 3 Result

TASK 3 implements the TenBagger screener and alpha validation layer.

## Implemented

- `HardFilter` with structural pass/fail diagnostics.
- Industry Factor V2:
  - industry growth score
  - industry valuation score
  - industry flow proxy score
- Momentum V2:
  - 1M return
  - 3M return
  - 6M return
  - weighted momentum score
- Revised TenBagger score weights:
  - 0.35 growth
  - 0.25 quality
  - 0.15 value
  - 0.10 industry
  - 0.10 momentum
  - 0.05 risk
- Debt-ratio ingestion from TuShare balance sheet.
- IC / RankIC validation for 21D, 63D, and 126D horizons.
- IC decay curve.
- Non-overlapping 21D simple backtest preview.
- Screener parquet outputs under local `data/screener/`.
- Web dashboard support for screener candidates, IC decay, and preview return.

## Validation Run

Commands:

```powershell
python scripts/run_task1.py --limit 10 --start-date 20230101
python scripts/run_task2.py
python scripts/run_task3.py
```

TASK 3 result:

```json
{
  "stock_count": 10,
  "row_count": 8390,
  "latest_trading_date": "2026-06-24",
  "candidate_count": 1,
  "ic_decay_curve": [
    {
      "horizon_days": 21,
      "ic_mean": 0.051200282601937784,
      "rank_ic_mean": 0.023376336585581747,
      "observations": 818
    },
    {
      "horizon_days": 63,
      "ic_mean": 0.042292218240942286,
      "rank_ic_mean": 0.04950718591008934,
      "observations": 776
    },
    {
      "horizon_days": 126,
      "ic_mean": 0.10054005799549033,
      "rank_ic_mean": 0.07240158848356969,
      "observations": 713
    }
  ],
  "backtest_preview": {
    "top_decile_return": -0.0010216931614421632,
    "benchmark_return": -0.001071345144169689,
    "excess_return": 0.00004965198272752582,
    "max_drawdown": -0.29596437701213263,
    "observations": 39
  }
}
```

Filtered candidate:

```text
300750.SZ  score=73.33  industry=电气设备  revenue_growth_yoy=0.5245  roe=5.9731  debt_ratio=0.6232
```

Test command:

```powershell
python -m pytest -q
```

Result:

```text
7 passed
```
