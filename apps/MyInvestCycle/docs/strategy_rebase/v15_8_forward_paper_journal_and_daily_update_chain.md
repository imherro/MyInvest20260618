# V15.8 Forward Paper Journal and Daily Update Chain

## Purpose

V15.8 turns the V15.7 single-day forward snapshot into an append-only cross-day observation journal. It preserves one immutable paper-only record per decision date so future outcomes can be attached without rewriting the original observation.

## Daily chain

`scripts/run_v15_daily_forward_update.py` performs one explicit command chain:

1. Build or revalidate the V15.7 daily snapshot.
2. Write the latest V15.7 capture status and paper-only decision.
3. Build the V15.8 journal record from the verified manifest and paper decision.
4. Append a new record or validate the existing identical record.
5. Recompute and write journal status from the JSONL records.

The script is not a scheduler or background service.

## Append-only rules

- `record_id` binds `decision_date` to `snapshot_manifest_sha256`.
- The same `record_id` is idempotent and never appends or rewrites a line.
- The same decision date with a different manifest hash is rejected.
- Each record must reference an existing manifest whose normalized hash is valid.
- Counts and latest-date fields are recomputed from the journal, not trusted from status input.

## Outcome boundary

Each record starts with pending T+1, T+5, and T+20 windows. V15.8 does not calculate returns, evaluate outcomes, run a backtest, optimize parameters, or generate positions, weights, instruments, signals, orders, broker actions, or trading advice.

## Outputs

- `data/v15_forward_observation_journal.jsonl`
- `data/v15_forward_observation_journal_status.json`
- `GET /api/strategy-rebase/v15-forward-observation-journal`
- compact summary key `v15_forward_observation_journal`

The validation page extends the existing V15.7 card with record count, latest decision date, and pending-outcome count.
