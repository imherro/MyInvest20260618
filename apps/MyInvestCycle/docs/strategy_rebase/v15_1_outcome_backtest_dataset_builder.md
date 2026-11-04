# V15.1 Outcome-Oriented Backtest Dataset Builder

## Purpose

V15.1 defines the data manifest required for V15+ outcome-oriented backtests.

It does not fetch a full dataset, run a strategy, produce returns, generate positions, map funds, generate portfolio weights, create allocation output, create trade signals, create orders or connect to a broker.

## Dataset Groups

- broad indices: market baselines and long-cycle drawdown context
- sector indices: sector/theme strength and structural bull rotation breadth
- macro cycle: long-term macro and valuation context
- drawdown context: bull-market pullback versus late-cycle or bear-market risk
- structural bull: broad-index stagnation with strong sector/theme mainlines

## Future Backtest Targets

- macro plus drawdown strategy
- structural bull rotation strategy
- old strategy baseline

## Data Quality Requirements

Future V15 backtests must use point-in-time data, release-date safe macro fields, survivorship-bias checks and cache consistency checks. Missing or stale data must be disclosed instead of treated as a successful update.

## Boundary

V15.1 is only a manifest. Production trading remains disabled.
