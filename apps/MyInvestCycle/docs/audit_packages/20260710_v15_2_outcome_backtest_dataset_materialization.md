请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V15.2 Outcome Backtest Dataset Materialization Audit Package

## Task

TASK V15.2 - Outcome Backtest Dataset Materialization.

V15.2 builds a local coverage/materialization status report for the V15.1 dataset manifest. It reads existing local cache/report files and records coverage, field visibility, date ranges and hashes. It does not fetch full datasets, run strategy, produce returns, generate positions, generate portfolio weights, output trade signals, create orders or connect a broker.

## Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Previous audited V15.1 commit: `318a48c98b22f4b841915a3b8cb09774228b1425`
- Expected commit title: `Add V15.2 outcome dataset materialization status`

## Added Files

- `strategy_rebase/backtest_dataset_materializer.py`
- `scripts/run_v15_backtest_dataset_materializer.py`
- `scripts/test_v15_backtest_dataset_materializer.py`
- `data/v15_backtest_dataset_materialization_status.json`
- `docs/strategy_rebase/v15_2_outcome_backtest_dataset_materialization.md`
- `docs/audit_packages/20260710_v15_2_outcome_backtest_dataset_materialization.md`

## Modified Files

- `strategy_rebase/__init__.py`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`

## Output Contract

Generated artifact: `data/v15_backtest_dataset_materialization_status.json`

Required fields:

- `phase = V15.2`
- `materialization_status = coverage_report_ready`
- `source_manifest = data/v15_backtest_dataset_manifest.json`
- `dataset_groups_checked = 5`
- `full_dataset_fetched = false`
- `strategy_run = false`
- `backtest_result_generated = false`
- `position_generated = false`
- `trade_signal_generated = false`
- `production_trade_enabled = false`

Coverage groups:

- `broad_indices`
- `sector_indices`
- `macro_cycle`
- `drawdown_context`
- `structural_bull`

Current local coverage summary:

- source count: `29`
- available source count: `29`
- missing source count: `0`
- coverage ratio: `1.0`

Important caveat: this is file-level/local-source coverage only. V15.2 does not claim semantic field mapping is complete and does not claim any strategy return result.

## Safety And Boundary

V15.2 explicitly keeps:

- `full_dataset_fetched = false`
- `strategy_run = false`
- `backtest_result_generated = false`
- `position_generated = false`
- `trade_signal_generated = false`
- `production_trade_enabled = false`
- `constraints.no_broker_connection = true`

It also records:

- `point_in_time_check_defined = true`
- `release_date_alignment_defined = true`
- `survivorship_bias_check_defined = true`
- `missing_field_report_defined = true`
- `source_hash_recorded = true`
- `cache_hash_recorded = true`
- `no_live_fetch_attempted = true`

## Web/API Exposure

- Added `GET /api/strategy-rebase/v15-dataset-materialization`
- Added the endpoint to `GET /api`
- Added compact summary key `v15_backtest_dataset_materialization` to `GET /api/results/summary?compact=true`
- Added `/validation` card title `V15.2 回测数据落地状态`

## Verification

Passed locally:

```text
python scripts\run_v15_backtest_dataset_materializer.py
python scripts\test_v15_backtest_dataset_materializer.py
python scripts\test_v15_backtest_dataset_builder.py
python scripts\test_v15_strategy_direction_rebase.py
python -m py_compile strategy_rebase\__init__.py strategy_rebase\outcome_objectives.py strategy_rebase\backtest_dataset_builder.py strategy_rebase\backtest_dataset_materializer.py scripts\run_v15_backtest_dataset_materializer.py scripts\test_v15_backtest_dataset_materializer.py web\app.py
node --check web\static\dashboard.js
python -m compileall strategy_rebase scripts web
python scripts\test_risk_diagnostic_shadow_evidence_dashboard.py
python scripts\test_risk_diagnostic_shadow_event_input_package.py
python scripts\test_risk_diagnostic_shadow_first_event_workflow.py
python scripts\test_research_to_implementation_boundary.py
```

Observed generator output:

```text
V15.2 backtest dataset materialization status written to C:\Users\kunpeng\Documents\MyInvestCycle\data\v15_backtest_dataset_materialization_status.json | phase=V15.2 status=coverage_report_ready groups=5 sources=29/29 full_dataset_fetched=False strategy_run=False position_generated=False trade_signal_generated=False trade=False audit=passed
```

8021 smoke test passed:

- `/api/strategy-rebase/v15-dataset-materialization` returned 200
- `phase = V15.2`
- `materialization_status = coverage_report_ready`
- `dataset_groups_checked = 5`
- source count = 29
- available source count = 29
- `full_dataset_fetched = false`
- `strategy_run = false`
- `backtest_result_generated = false`
- `position_generated = false`
- `trade_signal_generated = false`
- `production_trade_enabled = false`
- `/api` includes `/api/strategy-rebase/v15-dataset-materialization`
- `/api/results/summary?compact=true` includes `v15_backtest_dataset_materialization`
- `/validation` includes card title `V15.2 回测数据落地状态`

## Known Local State

- `data/structural_survival_dataset.json` was already locally modified before this V15.2 task. It is unrelated and intentionally left unstaged/uncommitted.
- V15.2 source specs intentionally exclude `data/structural_survival_dataset.json`, so the committed V15.2 materialization artifact does not depend on that dirty local file.

## Review Questions

1. Please verify that V15.2 is only a local coverage/materialization status report and does not run strategy/backtest/position/trade logic.
2. Please verify whether `data/v15_backtest_dataset_materialization_status.json` is suitable as the readiness input for the next V15 strategy-backtest task.
3. If approved, please provide the next development task. If this is enough, explicitly say the project is complete.
