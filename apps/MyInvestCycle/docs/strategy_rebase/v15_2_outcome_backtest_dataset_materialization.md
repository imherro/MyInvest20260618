# V15.2 Outcome Backtest Dataset Materialization

## Purpose

V15.2 turns the V15.1 dataset manifest into a local coverage and materialization status report.

It reads existing local cache/report files, records source coverage, missing-field reports and cache hashes, and defines point-in-time safety checks for future backtests.

V15.2 still does not run any strategy, compute a return curve, generate positions, map ETFs, generate portfolio weights, produce trade signals, create orders or connect to a broker.

## Output

Generated artifact:

- `data/v15_backtest_dataset_materialization_status.json`

Status:

- `phase = V15.2`
- `materialization_status = coverage_report_ready`
- `full_dataset_fetched = false`
- `strategy_run = false`
- `backtest_result_generated = false`
- `position_generated = false`
- `trade_signal_generated = false`
- `production_trade_enabled = false`

## Coverage Groups

- broad indices
- sector indices
- macro cycle
- drawdown context
- structural bull

Each group reports local sources, availability, row/key samples, date ranges when observable, missing manifest-field matches and cache hashes.

## Boundary

This phase is a data-readiness report, not an investment strategy.

The existing `data/structural_survival_dataset.json` local modification is intentionally not used as a V15.2 source, so the committed materialization artifact does not depend on that unrelated dirty working-tree file.
