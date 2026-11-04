# TASK 4 Result

TASK 4 implements the portfolio simulation backtest layer.

## Implemented

- `PortfolioBuilder`
  - top-K portfolio construction
  - monthly walk-forward rebalance
  - equal, score, and volatility-adjusted weighting
- Transaction simulation
  - turnover
  - transaction cost, default 0.2%
  - slippage, default 0.05%
- Portfolio NAV output
- Benchmark comparison
  - CSI300
  - CSI500
- Risk metrics
  - annual return
  - Sharpe ratio
  - max drawdown
  - volatility
  - beta vs benchmark
  - win rate
  - turnover rate
- Factor attribution
  - dominant factor
  - rolling factor contribution
- Web dashboard support for TASK 4.

## Validation Run

Commands:

```powershell
python scripts/run_task1.py --limit 10 --start-date 20230101
python scripts/run_task2.py
python scripts/run_task3.py
python scripts/run_task4.py --top-k 10 --weight-mode score
```

Result:

```json
{
  "date_range": {
    "start": "2023-02-01",
    "end": "2026-06-24"
  },
  "nav_rows": 823,
  "rebalance_count": 41,
  "final_nav": 0.8106125937658355,
  "metrics": {
    "annual_return": -0.06426946557608848,
    "sharpe": -0.25527299307697016,
    "max_drawdown": -0.28358937916398996,
    "volatility": 0.18480878624130323,
    "win_rate": 0.45443499392466585,
    "turnover_rate": 0.0539318594596711,
    "total_transaction_cost": 0.0055280155946162875
  },
  "benchmarks": {
    "CSI300": {
      "annual_return": 0.05265623955702625,
      "excess_return": -0.11692570513311473,
      "beta": 0.8742809442074316,
      "max_drawdown": -0.2444070342094703
    },
    "CSI500": {
      "annual_return": 0.10578333892888647,
      "excess_return": -0.17005280450497495,
      "beta": 0.48782430261710236,
      "max_drawdown": -0.3114731480389472
    }
  },
  "dominant_factor": "growth"
}
```

Interpretation:

- The portfolio engine is operational.
- Current factor model did not beat CSI300 or CSI500 in this sample.
- This validates the need for TASK 5 factor optimization rather than treating
  the current signal as trading-ready.

Test command:

```powershell
python -m pytest -q
```

Result:

```text
9 passed
```
