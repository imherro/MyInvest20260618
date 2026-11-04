# V15.9 Forward Outcome Intake MVP

## Purpose

V15.9 fills real CSI300 market outcomes for the immutable V15.8 forward observations. It writes a separate sidecar and never modifies the V15.8 journal.

## Windows

For each journal record, V15.9 creates T+1, T+5, and T+20 outcome records. The start is the latest CSI300 trading day on or before the decision date. The target is the Nth trading day after that start.

If the source, start, or target is unavailable, the window remains pending with all result fields null. If the target exists, the sidecar records the two dates, closes, deterministic benchmark return, and a SHA-256 hash of the exact two source rows used as evidence.

## Update semantics

- `pending -> pending`: idempotent.
- `pending -> completed`: allowed after benchmark evidence becomes available.
- `completed -> completed`: must be exactly identical.
- `completed -> pending` or changed completed evidence: rejected.
- Duplicate `outcome_id` rows are rejected.
- Candidate records are fully validated before the sidecar is atomically replaced.

The source evidence hash is based on the exact start/end rows, so appending later market dates does not invalidate an already completed window.

## Boundary

The recorded value is a CSI300 market result, not strategy return, alpha, portfolio return, position return, win-rate evidence, allocation advice, or a trading signal. Backtesting and production trading remain disabled.

## Outputs

- `data/v15_forward_outcome_records.jsonl`
- `data/v15_forward_outcome_status.json`
- `GET /api/strategy-rebase/v15-forward-outcomes`
- compact summary key `v15_forward_outcomes`
