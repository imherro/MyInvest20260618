# Opportunity Research V7 Architecture Freeze

## Freeze Status

V7 opportunity research is frozen at `V7.5 Opportunity Research Layer Freeze & Audit Summary`.

This layer is research-only. It keeps the asset universe, feature construction, feature validation, and feature attribution framework, but it does not create an investable opportunity engine.

## Retained Layers

### V7.1 Asset Research Foundation

- Keeps the ETF asset universe and long-history research proxy layer.
- Separates research proxy history from tradable ETF history.
- Records coverage blockers and time-safety boundaries.
- Output boundary: no opportunity score, no rank, no allocation, no trade.

### V7.2 Context Features

- Keeps fixed opportunity context feature groups:
  - momentum
  - relative_strength
  - trend
  - risk
  - structure
- Records source, source kind, as-of date, and feature completeness.
- Uses V6 context as metadata only, not as joined asset feature values.
- Output boundary: no opportunity score, no rank, no Top N, no allocation, no trade.

### V7.3 Feature Validation

- Keeps fixed 5/20/60 trading-day IC validation.
- Separates research proxy validation from tradable ETF validation.
- Uses future returns only as validation labels, not as feature inputs.
- Output boundary: effectiveness labels only; no opportunity score, no rank, no allocation, no trade.

### V7.4 Feature Attribution

- Keeps retention labels:
  - research_candidate
  - watch
  - reject_for_now
  - insufficient
- Keeps regime consistency attribution.
- Records the conclusion `feature_attribution_not_ready_for_opportunity_score`.
- Output boundary: retention labels are not scores, weights, ranks, Top N, allocation, or trading instructions.

## Explicit Rejections

- Opportunity Score: rejected because feature stability is insufficient.
- Ranking: rejected because no validated alpha or opportunity layer exists.
- Top N: rejected because it would be implicit asset selection without validated ranking power.
- Allocation: rejected because no opportunity engine has been validated.
- ETF weight: rejected because feature attribution does not define tradable weights.
- Trading: rejected because this project layer is research-only and does not connect to brokers or order generation.
- New feature search: rejected in V7 freeze because more feature mining would increase overfitting risk before the existing fixed features prove stable.

## Verified By V7

- Asset research foundation.
- Proxy and tradable history separation.
- Fixed feature audit framework.
- Time-safe feature construction.
- IC-based feature effectiveness audit.
- Feature retention and regime consistency attribution.

## Not Verified By V7

- Opportunity prediction.
- Asset ranking.
- Top N asset selection.
- Allocation alpha.
- ETF weight generation.
- Tradable strategy improvement.
- Trading signal generation.

## Current Evidence Summary

- V7.1 established 17 research assets and separated research proxies from tradable ETF histories.
- V7.2 generated fixed feature groups on a resolved safe date without scoring or ranking.
- V7.3 produced 42 feature-horizon validation rows, with most results flat, weak, or insufficient.
- V7.4 produced 42 attribution rows:
  - research_candidate: 1
  - watch: 17
  - reject_for_now: 18
  - insufficient: 6
- V7.4 conclusion: `feature_attribution_not_ready_for_opportunity_score`.

## Frozen Constraints

The V7 layer must keep these constraints:

- no new feature
- no Opportunity Score
- no score
- no rank
- no Top N
- no allocation
- no ETF weight
- no portfolio weight
- no trading
- no order generation
- no broker connection
- no parameter optimization for investable output

## Future Direction

The next research direction should not extend V7 into a score. If work continues, it should start a separate V8 research design that integrates V6 risk context and the V7 opportunity research foundation.

V8 can discuss decision or allocation research, but it must begin as an audit layer and remain non-trading until validated evidence proves incremental alpha, drawdown improvement, and stability.
