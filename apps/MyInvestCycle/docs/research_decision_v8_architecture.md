# Research Decision V8 Architecture Freeze

## Freeze Status

V8 research decision integration is frozen at `V8.4 Research Decision Architecture Freeze & Summary`.

This layer is research-interpretation only. It connects frozen V6 risk context and frozen V7 opportunity research, explains historical scenario consistency, and attributes selected contradiction cases. It does not create a decision engine.

## Retained Layers

### V8.1 Research Decision Context

- Keeps the research context `risk_controlled_opportunity_watch`.
- Keeps the posture `observe_without_selection`.
- Connects V6 risk context and V7 opportunity research status.
- Output boundary: no score, no ranking, no asset selection, no allocation, no ETF weight, no trade.

### V8.2 Historical Scenario Audit

- Keeps fixed historical scenarios:
  - 2015 bull-bear transition
  - 2018 bear
  - 2020 recovery
  - 2021 core asset divergence
  - 2022 bear
  - 2024-2026 structural market
- Keeps consistency, transition, contradiction, and coverage diagnostics.
- Output boundary: no return metric, no score, no strategy, no allocation, no trade.

### V8.3 Contradiction Attribution

- Keeps failure attribution for selected scenarios.
- Keeps contradiction types and possible reasons.
- Keeps the conclusion `contradiction_attribution_research_only_no_rule_change`.
- Output boundary: no rule change, no new state, no V6/V7 mutation, no score, no ranking, no allocation, no trade.

## Explicit Rejections

- Score: rejected because V8 explains context and contradictions but does not prove predictive power.
- Ranking: rejected because V7 opportunity ranking remains unverified.
- Asset Selection: rejected because V8 does not output assets.
- Top N: rejected because no validated ranking layer exists.
- Allocation: rejected because V8 is not an allocation engine.
- ETF Weight: rejected because V8 produces no tradable weights.
- Trading: rejected because this layer is research-only.
- New State: rejected because V8.3 explains failures without changing state taxonomy.
- V6/V7 Modification: rejected because V8 consumes frozen V6/V7 artifacts only.

## Verified By V8

- V6 and V7 can be connected as a research interpretation layer.
- Historical scenario consistency can be audited without returns.
- Contradiction cases can be attributed without rule changes.
- The current architecture can explain some failures but is not stable enough for strategy.

## Not Verified By V8

- Predictive decision engine.
- Opportunity score.
- Asset ranking.
- Asset selection.
- Allocation alpha.
- ETF weight generation.
- Trading signal generation.

## Current Evidence Summary

- V8.1 decision context: `risk_controlled_opportunity_watch`.
- V8.1 posture: `observe_without_selection`.
- V8.2 scenarios: 6 covered.
- V8.2 consistency: medium 3 / low 3.
- V8.2 conclusion: `scenario_explanation_audit_only_no_strategy`.
- V8.3 focus scenarios: 5.
- V8.3 attribution rows: 5.
- V8.3 conclusion: `contradiction_attribution_research_only_no_rule_change`.

## Frozen Constraints

The V8 layer must keep these constraints:

- no score
- no ranking
- no asset selection
- no Top N
- no allocation
- no ETF weight
- no portfolio weight
- no trading
- no order generation
- no broker connection
- no V6 mutation
- no V7 mutation
- no new state
- no parameter optimization for investable output

## Future Direction

Future work should start a separate phase if it wants to research allocation. That future phase must begin with a new audit design and cannot treat V8 as a strategy or trading decision engine.
