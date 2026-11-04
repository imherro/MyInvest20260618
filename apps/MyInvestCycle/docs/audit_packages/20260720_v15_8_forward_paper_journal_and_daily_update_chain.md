# V15.8 Audit Package

## Scope

V15.8 adds one append-only forward observation journal and one explicit daily command chain. It does not add a scheduler, backtest, return evaluation, allocation, position, instrument mapping, signal, order, broker connection, or production trading behavior.

## Generated result

- Journal: `data/v15_forward_observation_journal.jsonl`
- Status: `data/v15_forward_observation_journal_status.json`
- `record_count`: 1
- `unique_decision_date_count`: 1
- `latest_decision_date`: `20260720`
- `pending_outcome_count`: 1
- `completed_outcome_count`: 0
- `duplicate_record_count`: 0
- `append_only_mode`: true
- `backtest_allowed`: false
- `production_trade_enabled`: false

The first record references manifest hash `093860a5cac4abb95163a91e932c04b9ea7358e260596445c298de2983fecb87`.

## Validation coverage

- First run creates the first journal record.
- Same record rerun does not append or rewrite bytes.
- Same decision date with another manifest hash is rejected.
- Missing manifest and mismatched manifest hash are rejected.
- Every forbidden key is injected below a nested object and rejected.
- Backtest, production trade, record count, unique-date count, and pending count forgeries are rejected.
- Journal status is rebuilt from JSONL content.
- New records are validated before append.

## Web boundary

The only new endpoint is `GET /api/strategy-rebase/v15-forward-observation-journal`. The existing V15.7 validation card receives three status rows. No new page or dashboard is introduced.

## Known unrelated local change

`data/structural_survival_dataset.json` remains unstaged and is not part of V15.8.
