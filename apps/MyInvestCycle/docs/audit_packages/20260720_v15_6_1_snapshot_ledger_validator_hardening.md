# V15.6.1 Snapshot Ledger Validator Hardening

## Scope

This patch only hardens the existing V15.6 validator. It adds no strategy, backtest, position, trade, order, broker, framework, or Web surface.

## Validator changes

- Recompute every source group's lineage from raw nested fields.
- Require a 64-character hexadecimal historical snapshot SHA-256.
- Compare stored group flags, row flags, snapshot flags, and missing-source lists with computed values.
- Recompute complete, eligible, verified-hash, and valuation counts before comparing status.
- Require `backtest_allowed=false` and `promotion_ready=false` for every V15.6 ledger.

## Anti-forgery coverage

Tests reject forged row completion flags, forged group flags, forged status counts, an enabled backtest gate, an invalid SHA-256, and a missing-source list that disagrees with computed gaps.

## Expected result

- `ledger_status=ledger_gap_report_ready`
- decision dates: 140
- complete snapshots: 0
- strict point-in-time eligible dates: 0
- verified historical hashes: 0
- valuation snapshots: 0
- backtest allowed: false
- promotion ready: false
