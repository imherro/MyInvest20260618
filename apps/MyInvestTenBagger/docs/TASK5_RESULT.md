# TASK 5 Result

TASK 5 implements factor neutralization and walk-forward weight optimization.

## Implemented

- Factor neutralization layer:
  - industry neutralization
  - market-cap bucket neutralization
  - beta-proxy bucket neutralization
- Factor weight optimizer:
  - coarse grid search
  - walk-forward train/test split
  - no full-sample optimization
  - max single-factor weight cap of 0.50
- Regime detector:
  - bull / bear / sideways
  - growth-driven / value-driven / balanced
- Dynamic weight system:
  - regime-aware weight adjustment
- IC comparison:
  - baseline vs optimized
  - 21D / 63D / 126D RankIC deltas
- Web dashboard support for TASK 5.

## Validation Run

Command:

```powershell
python scripts/run_task5.py
```

Result:

```json
{
  "candidates_evaluated": 90,
  "best_weights": {
    "growth_score": 0.0,
    "quality_score": 0.0,
    "value_score": 0.0,
    "industry_score": 0.0,
    "momentum_score": 0.5,
    "risk_score": 0.5
  },
  "baseline_test_metrics": {
    "annual_return": -0.17661544317349898,
    "sharpe": -1.1318810617122008,
    "max_drawdown": -0.19649516983642634
  },
  "optimized_test_metrics": {
    "annual_return": -0.17836489843696413,
    "sharpe": -1.2228826514248032,
    "max_drawdown": -0.19942469386558181
  },
  "rank_ic_delta": {
    "21d": 0.06657455807823805,
    "63d": 0.03896939156382568,
    "126d": 0.07060807354824915
  }
}
```

Interpretation:

- RankIC improved materially after neutralization and optimization.
- Portfolio test performance did not improve.
- This means the optimized signal has better cross-sectional ordering, but the
  current portfolio construction and small universe still do not monetize the
  signal.
- The result is intentionally not overfit with test-set feedback.

Test command:

```powershell
python -m pytest -q
```

Result:

```text
12 passed
```
