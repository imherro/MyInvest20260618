# TASK 8 Result

TASK 8 starts route 2: behavioral finance and structural market modeling.

## Implemented

- Market index data loader:
  - CSI300
  - CSI500
  - TuShare index cache under `data/regime/`
- Trend Regime Engine:
  - 20D / 60D / 120D moving-average slope
  - 20D / 60D / 120D rolling returns
  - trend persistence
- Volatility Regime Engine:
  - 20D / 60D realized volatility
  - rolling historical volatility percentile
- Liquidity Regime Engine:
  - turnover / amount proxy
  - 20D / 60D liquidity ratio
  - rolling liquidity percentile
- Behavioral State Classifier:
  - risk_on
  - risk_off
  - panic
  - euphoria
  - transition
- Regime Transition Detector:
  - regime change probability
  - stability score
- Statistical validation:
  - regime autocorrelation
  - duration distribution
  - transition frequency
- Web dashboard support:
  - `GET /api/task8/regime`
  - Market Regime Dashboard section on port `8020`

## Validation Run

Command:

```powershell
python scripts/run_task8.py
```

TASK 8 writes:

- `reports/task8_regime_summary.json`
- `reports/TASK8_REGIME_REPORT.md`
- `data/regime/market_regime_daily.parquet`

Current local result:

```json
{
  "date": "2026-06-24",
  "trend_regime": "bull",
  "volatility_regime": "high",
  "liquidity_regime": "expansion",
  "behavior_state": "transition",
  "regime_change_probability": 0.2287,
  "stability_score": 0.9,
  "trend_strength": 0.445,
  "volatility_percentile": 0.8968,
  "liquidity_score": 0.9934
}
```

Stability validation:

```json
{
  "regime_autocorrelation": 0.8681,
  "transition_frequency": 0.132,
  "recent_30d_transition_frequency": 0.1667,
  "mean_duration_days": 7.5203,
  "transition_not_overfit": true,
  "regime_has_continuity": true
}
```

Interpretation:

- TASK 8 does not predict individual stocks.
- It converts market price, volatility, and liquidity data into an interpretable
  market behavior state.
- The model uses trailing windows only and does not use future return labels.
