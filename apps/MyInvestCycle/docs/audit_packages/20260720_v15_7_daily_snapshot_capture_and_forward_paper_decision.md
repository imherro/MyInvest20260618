# V15.7 Daily Snapshot Capture and Forward Paper Decision

## Scope

V15.7 captures five currently available local sources into a dated immutable directory, verifies file hashes, and writes a paper-only forward observation. It adds no backtest, optimizer, position, portfolio weight, instrument mapping, order, or broker connection.

## Verification targets

- Missing input remains missing and produces no fake snapshot file.
- Every available copied file has a recomputable SHA-256.
- The manifest hash is derived from canonical JSON excluding only `manifest_sha256`.
- Re-running the same date does not overwrite the snapshot.
- The paper decision contains no forbidden stock, ETF, weight, signal, order, or rebalance keys.
- Backtesting and production trading remain disabled.

## Expected current result

- Snapshot date: 20260720
- Configured sources: 5
- Paper decision status: insufficient_for_trade_decision
- Allowed use: forward_observation_only
