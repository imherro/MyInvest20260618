# V15.9 Audit Package

## Result

- Journal records: 1
- Outcome records: 3
- Completed outcomes: 0
- Pending outcomes: 3
- Latest decision date: `20260720`
- Benchmark: `CSI300`
- Paper only: true
- Backtest allowed: false
- Production trade enabled: false

The local CSI300 cache currently ends at `20260708`, before the `20260720` decision date. V15.9 therefore keeps T+1, T+5, and T+20 pending rather than treating stale data as a future result.

## Integrity checks

- V15.8 journal and manifest validation runs before intake.
- The original journal bytes are checked and never changed.
- Exactly three deterministic windows are required per journal record.
- Pending windows cannot claim dates, prices, returns, or hashes.
- Completed windows are recomputed from the fixed trading-day offset.
- Completed evidence hashes bind the exact start/end rows.
- Only pending-to-completed transitions are allowed.
- Duplicate IDs, changed completed results, forged counts, strategy-return keys, and trade keys are rejected.
- The sidecar is validated before atomic replacement.

## Web scope

Only one read-only status API and three rows in the existing V15.7/V15.8 card are added. No page, dashboard, strategy, position, or trading surface is introduced.

## Known unrelated local change

`data/structural_survival_dataset.json` remains unstaged and is not part of V15.9.
