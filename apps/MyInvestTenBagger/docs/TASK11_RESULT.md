# TASK 11 Result

TASK 11 implements the market structural anomaly detection layer for route 2.

## Implemented

- Structural break detection:
  - trend break
  - volatility regime shift
  - liquidity collapse
- Correlation breakdown detector:
  - correlation spike
  - cross-sector decoupling
  - systemic risk emergence
- Flow shock detection:
  - institutional flow shock
  - retail panic cluster
  - liquidity vacuum
- Behavioral anomaly engine:
  - irrational FOMO spike
  - panic cascade
  - breakout failure cluster
- Multi-layer anomaly fusion:
  - regime + behavior + structure anomaly score
  - systemic risk level
- Validation:
  - no future return labels
  - no alpha model
  - no market direction prediction
  - purely observational
  - walk-forward features only
- Web dashboard support:
  - `GET /api/task11/anomaly`
  - Structural Anomaly Dashboard section on port `8020`

## Validation Run

Command:

```powershell
python scripts/run_task11.py
```

TASK 11 writes:

- `reports/task11_anomaly_summary.json`
- `reports/TASK11_ANOMALY_REPORT.md`
- `data/anomaly/market_anomaly_daily.parquet`

Current local result:

```json
{
  "date": "2026-06-24",
  "structural_break_prob": 0.0747,
  "correlation_break_prob": 0.117,
  "flow_shock_prob": 0.0727,
  "behavioral_anomaly_score": 0.1798,
  "anomaly_score": 0.1112,
  "systemic_risk_level": "low",
  "dominant_anomaly_type": "none",
  "anomaly_state": "low::none",
  "cross_sector_decoupling_prob": 0.7001,
  "liquidity_vacuum_prob": 0.0066
}
```

Validation:

```json
{
  "uses_future_return_labels": false,
  "uses_alpha_model": false,
  "predicts_market_direction": false,
  "purely_observational": true,
  "walk_forward_features_only": true,
  "anomaly_is_structure_deviation": true,
  "all_scores_bounded_0_1": true,
  "anomaly_state_autocorrelation": 0.9676,
  "anomaly_transition_frequency": 0.0325,
  "anomaly_event_frequency": 0.0,
  "high_risk_frequency": 0.0
}
```

Interpretation:

- TASK 11 does not forecast future returns.
- It detects deviations from the current market structure, not profit signals.
