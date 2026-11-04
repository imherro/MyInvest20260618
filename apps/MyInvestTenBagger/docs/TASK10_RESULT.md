# TASK 10 Result

TASK 10 implements the market structure decomposition layer for route 2.

## Implemented

- Return decomposition engine:
  - trend component
  - flow component
  - volatility component
  - noise component
- Market dispersion engine:
  - cross-sectional return dispersion
  - breadth / synchronization
  - industry dispersion
- Correlation structure engine:
  - rolling cross-sectional correlation
  - correlation regime
  - correlation spike score
- Market regime interaction model:
  - combines TASK 8 regime with TASK 9 behavior
  - produces a joint regime-behavior-structure state
- Structural shock detector:
  - volatility shift
  - correlation spike
  - dispersion spike
  - liquidity break
- Validation:
  - no future return labels
  - no alpha factors
  - purely observational
  - walk-forward features only
  - components sum to one
- Web dashboard support:
  - `GET /api/task10/structure`
  - Market Structure Dashboard section on port `8020`

## Validation Run

Command:

```powershell
python scripts/run_task10.py
```

TASK 10 writes:

- `reports/task10_structure_summary.json`
- `reports/TASK10_STRUCTURE_REPORT.md`
- `data/structure/market_structure_daily.parquet`

Current local result:

```json
{
  "date": "2026-06-24",
  "trend_component": 0.1229,
  "flow_component": 0.2996,
  "volatility_component": 0.3589,
  "noise_component": 0.2187,
  "market_dispersion": 0.9921,
  "correlation_regime": "medium",
  "cross_sectional_correlation": 0.2943,
  "structure_state": "balanced_structure",
  "structural_shock_probability": 0.3433,
  "structural_shock_type": "none",
  "regime_behavior_structure": "transition::neutral_behavior::balanced_structure"
}
```

Validation:

```json
{
  "uses_future_return_labels": false,
  "uses_alpha_factors": false,
  "walk_forward_features_only": true,
  "purely_observational": true,
  "components_sum_to_one": true,
  "all_scores_bounded_0_1": true,
  "structure_autocorrelation": 0.7622,
  "structure_transition_frequency": 0.2381,
  "shock_event_frequency": 0.0043
}
```

Interpretation:

- TASK 10 does not forecast future returns.
- It explains current market movement as a mixture of trend, flow,
  volatility, and noise structure.
- It uses local stock return dispersion and rolling correlation as structural
  market diagnostics.
