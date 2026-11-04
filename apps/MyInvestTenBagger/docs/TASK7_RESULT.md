# TASK 7 Result

TASK 7 implements the structural alpha validation layer requested by the
reviewer.

## Implemented

- Multi-regime alpha test:
  - bull / bear / sideways market regimes
  - growth-driven / value-driven / balanced style regimes
- Strict out-of-sample evaluation using the post-70% date split.
- Subsample robustness:
  - by year
  - by volatility regime
  - by industry
- Alpha stability score:
  - IC variance
  - Sharpe variance
  - decay retention
- Randomization tests:
  - label shuffle
  - feature permutation
- Real-alpha criteria engine:
  - `REAL`
  - `PSEUDO`
  - `NO ALPHA`
- Failure-mode diagnosis:
  - cost failure
  - turnover failure
  - factor decay
  - permutation failure
  - PnL failure
- Web dashboard support for TASK 7.

## Validation Run

Command:

```powershell
python scripts/run_task7.py
```

Result from the current local data snapshot:

```json
{
  "classification": "NO ALPHA",
  "split_date": "2025-06-11",
  "actual_rank_ic_21d": 0.0024,
  "oos_sharpe": -1.0611,
  "oos_annual_return": -0.1331,
  "oos_max_drawdown": -0.1686,
  "label_shuffle_p_value": 0.505,
  "feature_permutation_p_value": 0.3861,
  "primary_failure": "no_structural_alpha"
}
```

Interpretation:

- TASK 7 is the final structural edge gate.
- The current local data does not show structural out-of-sample alpha.
- The OOS RankIC is near zero and the permutation tests do not reject random
  alternatives.
- The engineering system is complete enough to make the distinction, but the
  current investment signal should be treated as not validated.
