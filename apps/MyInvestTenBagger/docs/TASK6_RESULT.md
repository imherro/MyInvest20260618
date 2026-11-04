# TASK 6 Result

TASK 6 implements alpha monetization and execution optimization.

## Implemented

- Rebalance-frequency search:
  - weekly
  - biweekly
  - monthly
- Transaction-cost sensitivity:
  - 0.05% to 1.0%
  - slippage-aware backtest
- Position concentration modes:
  - equal
  - score
  - volatility adjusted
  - score convex
  - top heavy
- Nonlinear payoff detector:
  - momentum convexity
  - growth + momentum breakout
  - tail-event return profile
- Alpha decay model:
  - 21D / 63D / 126D RankIC curve
  - exponential decay estimate
- IC vs PnL divergence report.
- Web dashboard support for TASK 6.

## Validation Run

Command:

```powershell
python scripts/run_task6.py
```

Result:

```json
{
  "best_config": {
    "rebalance": "biweekly",
    "weight_mode": "volatility_adjusted",
    "transaction_cost_rate": 0.0005,
    "slippage_rate": 0.0005
  },
  "train_metrics": {
    "annual_return": 0.03594918881366804,
    "sharpe": 0.2936021955033492,
    "max_drawdown": -0.23112051059511218
  },
  "test_metrics": {
    "annual_return": -0.12456667719120695,
    "sharpe": -0.9381350380675347,
    "max_drawdown": -0.16862918875151656
  },
  "ic_pnl_divergence": {
    "rank_ic_21d": 0.0899508946638198,
    "test_sharpe": -0.9381350380675347,
    "test_annual_return": -0.12456667719120695,
    "interpretation": "ranking_signal_not_monetized"
  }
}
```

Interpretation:

- Monetization improved the test loss profile versus TASK 5, but did not turn
  the system into positive alpha.
- Best configuration lowers friction with biweekly rebalancing and
  volatility-adjusted sizing.
- The current signal remains a research alpha, not a trading-ready strategy.

Test command:

```powershell
python -m pytest -q
```

Result:

```text
15 passed
```
