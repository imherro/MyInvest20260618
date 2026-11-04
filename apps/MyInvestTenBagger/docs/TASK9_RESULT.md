# TASK 9 Result

TASK 9 implements the behavioral finance core layer for route 2.

## Implemented

- Retail vs institutional pressure model:
  - retail pressure index
  - institutional flow index
  - dominant actor classification
- Panic / FOMO indexes:
  - volatility spike
  - volume surge
  - reversal pressure
  - momentum acceleration
- Crowd behavior mapping:
  - crowding level
  - positioning crowdedness
  - reversal risk
- Flow-price divergence detector:
  - buying without price response
  - price up with flow down
  - aligned accumulation
  - aligned distribution
- Behavioral regime overlay:
  - combines TASK 8 market state with behavior pressure state
- Validation:
  - no future return labels
  - no factor alpha reuse
  - walk-forward observable market behavior only
  - all scores bounded between 0 and 1
- Web dashboard support:
  - `GET /api/task9/behavior`
  - Behavioral Flow Dashboard section on port `8020`

## Validation Run

Command:

```powershell
python scripts/run_task9.py
```

TASK 9 writes:

- `reports/task9_behavior_summary.json`
- `reports/TASK9_BEHAVIOR_REPORT.md`
- `data/behavior/market_behavior_daily.parquet`

Current local result:

```json
{
  "date": "2026-06-24",
  "retail_pressure": "institutional",
  "retail_pressure_index": 0.3655,
  "institutional_flow": 0.5483,
  "panic_index": 0.2698,
  "fomo_index": 0.43,
  "crowding_level": "medium",
  "positioning_crowdedness": 0.5738,
  "reversal_risk": 0.4894,
  "flow_price_divergence": "aligned_accumulation",
  "behavior_overlay_state": "neutral_behavior",
  "joint_regime_behavior": "transition::neutral_behavior"
}
```

Validation:

```json
{
  "uses_future_return_labels": false,
  "walk_forward_features_only": true,
  "uses_factor_alpha": false,
  "all_scores_bounded_0_1": true,
  "overlay_autocorrelation": 0.8032,
  "behavior_transition_frequency": 0.197,
  "divergence_event_frequency": 0.3297,
  "recent_30d_mean_panic": 0.2683,
  "recent_30d_mean_fomo": 0.3402
}
```

Interpretation:

- TASK 9 does not predict individual stock returns.
- It explains who appears to be pushing the current market state, using only
  observable market behavior and trailing windows.
