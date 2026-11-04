# V15.4 Macro + Drawdown Robustness And Walk-Forward Validation

## Purpose

V15.4 tests whether the V15.3 macro-cycle plus drawdown baseline is a stable research result or a narrow parameter accident. It does not add valuation, crowding, sector rotation, ETF selection, current positions, or trading instructions.

## Validation Design

- Carrier and phase inputs remain identical to V15.3.
- Every variant observes phase and CSI300 drawdown after close on day `t` and applies exposure to day `t+1` return.
- Drawdown trigger thresholds are scaled by `0.75`, `1.00`, and `1.25`.
- Exposure strength is scaled around neutral exposure `0.50` by `0.75`, `1.00`, and `1.25`, clipped to `[0, 1]`.
- The resulting neighborhood contains nine variants.
- Cost sensitivity is measured at `0`, `5`, `10`, and `15` basis points per one-way exposure change. The formal evaluation uses `15bp`.
- Annual walk-forward validation starts after five training years. For each test year, only earlier dates are used to select the highest training Calmar variant, with CAGR and shallower drawdown as tie breakers. A training maximum drawdown below `-45%` is rejected.

## Result

The nine variants are close to one another, so the baseline is not extremely parameter-sensitive:

- Default V15.3 CAGR at 15bp: `4.6728%`
- Best neighborhood CAGR: `4.8852%`
- Worst neighborhood CAGR: `4.2190%`
- CAGR range: `0.6662 percentage points`
- Default parameter rank: `5 / 9`

However, the default V15.3 parameter set ranks `9 / 9`. Nearby rules do not rescue the low absolute return; they only produce similarly weak outcomes.

At `15bp` one-way cost, the prior-data-only annual walk-forward result is:

- CAGR: `1.4767%`
- Annual alpha versus the aligned CSI300 total-return window: `0.6703%`
- Maximum drawdown: `-23.6302%`
- Calmar: `0.062493`
- The absolute sample-out return is below the 2% cash assumption.

The walk-forward series beats the weak aligned CSI300 total-return window, but not cash. Together with negative full-period alpha and unverified phase lineage, the formal evaluation status is `failed` and the promotion decision is `reject_promotion`.

## Point-In-Time Caveat

V15.4 re-applies `t+1` execution for every parameter variant and uses only pre-test-year rows for walk-forward selection. That timing boundary is verified in code and tests.

The historical phase series itself is not independently proven to be a strict publication-time dataset. `market_phase_snapshot.json` may contain reconstructed historical replay. V15.4 therefore records:

```text
strict_point_in_time_status = unverified
phase_history_strict_point_in_time_not_independently_verified = true
```

This caveat blocks strategy promotion even if headline metrics improve.

## Decision

V15.4 does not promote V15.3. The next research task should first establish publication-time lineage for historical macro phases, then test an independently defined valuation/crowding late-cycle overlay. Adding sector or ETF complexity before those checks would make attribution harder.

## Boundary

- Research backtest only.
- No production signal.
- No current position recommendation.
- No broker connection.
- No order generation.
- No intraday signal.
