# Model V2 Scoring Engine

Model V2 adds a parallel scoring layer without replacing the original V1
`tenbagger_score`.

## What Changed

- Adds hard eligibility gates before ranking:
  - enough price history
  - positive revenue growth
  - ROE above 5
  - debt ratio below 70%
  - drawdown no worse than -70%
  - core fundamental fields present
  - excluded financial and real-estate industries removed
- Adds refined component scores:
  - growth persistence
  - quality durability
  - industry-relative score
  - risk-control score
  - momentum score
  - market-state score
- Adds dynamic weight profiles:
  - `growth`
  - `balanced`
  - `defensive`
  - `transition`
- Adds candidate confidence grades:
  - `A`: strongest research priority
  - `B`: research candidate
  - `C`: watchlist
  - `D`: weak or failed gate

## New Columns

- `tenbagger_score_v2`
- `v2_eligible`
- `v2_confidence_grade`
- `v2_confidence_score`
- `v2_fail_reasons`
- `v2_growth_persistence_score`
- `v2_quality_durability_score`
- `v2_industry_relative_score`
- `v2_risk_control_score`
- `v2_momentum_score`
- `v2_market_state_score`
- `v2_weight_profile`

## Research Run Result

Latest research run:

- Universe: `research`
- Stocks loaded: 498
- Rows: 289,526
- Latest trading date: 2026-06-24
- V2 eligible count: 18
- V2 candidate count: 4
- Latest V2 grades:
  - B: 4
  - C: 116
  - D: 376

V2 RankIC versus V1:

| Horizon | V1 RankIC | V2 RankIC |
| --- | ---: | ---: |
| 21D | 0.0135 | 0.0250 |
| 63D | -0.0016 | 0.0254 |
| 126D | -0.0564 | -0.0294 |

Interpretation: V2 improves short and medium horizon ordering and reduces long
horizon damage, but it is still not a confirmed strong alpha model.

