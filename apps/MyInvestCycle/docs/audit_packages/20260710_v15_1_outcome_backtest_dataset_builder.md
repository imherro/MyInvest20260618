请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V15.1 Outcome Backtest Dataset Builder Audit Package

## Task

TASK V15.1 - Outcome-Oriented Backtest Dataset Builder.

V15.1 only builds the manifest for future V15+ outcome-oriented backtests. It must not run a strategy, produce positions, generate portfolio weights, output trade signals, create orders, connect a broker, or claim any backtest result.

## Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Previous audited V15.0 commit: `94499052273969bd4b122253afe4eef5276f9cf2`
- Expected commit title: `Add V15.1 outcome backtest dataset manifest`

## Added Files

- `strategy_rebase/backtest_dataset_builder.py`
- `scripts/run_v15_backtest_dataset_builder.py`
- `scripts/test_v15_backtest_dataset_builder.py`
- `data/v15_backtest_dataset_manifest.json`
- `docs/strategy_rebase/v15_1_outcome_backtest_dataset_builder.md`
- `docs/audit_packages/20260710_v15_1_outcome_backtest_dataset_builder.md`

## Modified Files

- `strategy_rebase/__init__.py`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`

## Manifest Contract

Generated artifact: `data/v15_backtest_dataset_manifest.json`

Required top-level fields:

- `phase = V15.1`
- `dataset_status = manifest_ready`
- `does_not_run_strategy = true`
- `does_not_generate_position = true`
- `does_not_generate_trade_signal = true`
- `no_backtest_result = true`
- `production_trade_enabled = false`

Required constraints:

- `dataset_builder_only = true`
- `does_not_fetch_full_dataset = true`
- `does_not_run_strategy = true`
- `no_backtest_result = true`
- `does_not_generate_position = true`
- `does_not_generate_fund_mapping = true`
- `does_not_generate_portfolio_weight = true`
- `no_allocation = true`
- `does_not_generate_trade_signal = true`
- `no_trade = true`
- `no_broker_connection = true`
- `production_trade_enabled = false`

Dataset groups:

- `broad_indices`
- `sector_indices`
- `macro_cycle`
- `drawdown_context`
- `structural_bull`

Future backtest targets:

- `macro_drawdown_strategy`
- `structural_bull_rotation_strategy`
- `old_strategy_baseline`

## API And Web Exposure

- Added `GET /api/strategy-rebase/v15-backtest-dataset`
- Added the endpoint to `GET /api`
- Added compact summary key `v15_backtest_dataset_manifest` to `GET /api/results/summary?compact=true`
- Added `/validation` card title `V15.1 回测数据集构建`

## Verification

Passed locally:

```text
python scripts\run_v15_backtest_dataset_builder.py
python scripts\test_v15_backtest_dataset_builder.py
python scripts\test_v15_strategy_direction_rebase.py
python -m py_compile strategy_rebase\__init__.py strategy_rebase\outcome_objectives.py strategy_rebase\backtest_dataset_builder.py scripts\run_v15_backtest_dataset_builder.py scripts\test_v15_backtest_dataset_builder.py web\app.py
node --check web\static\dashboard.js
python -m compileall strategy_rebase scripts web
python scripts\test_risk_diagnostic_shadow_evidence_dashboard.py
python scripts\test_research_to_implementation_boundary.py
```

Observed generator output:

```text
V15.1 backtest dataset manifest written to C:\Users\kunpeng\Documents\MyInvestCycle\data\v15_backtest_dataset_manifest.json | phase=V15.1 status=manifest_ready groups=5 no_strategy=True no_position=True no_trade_signal=True trade=False audit=passed
```

8021 smoke test passed:

- `/api/strategy-rebase/v15-backtest-dataset` returned 200
- `phase = V15.1`
- `dataset_status = manifest_ready`
- dataset group count = 5
- `does_not_run_strategy = true`
- `does_not_generate_position = true`
- `does_not_generate_trade_signal = true`
- `no_backtest_result = true`
- top-level `production_trade_enabled = false`
- summary `production_trade_enabled = false`
- `/api` includes `/api/strategy-rebase/v15-backtest-dataset`
- `/api/results/summary?compact=true` includes `v15_backtest_dataset_manifest`
- `/validation` includes card title `V15.1 回测数据集构建`

## Known Local State

- `data/structural_survival_dataset.json` was already locally modified before this V15.1 task. It is unrelated and intentionally left unstaged/uncommitted.

## Review Questions

1. Please verify that V15.1 contains only manifest/data-contract work and does not run strategy/backtest/position/trade logic.
2. Please verify that `data/v15_backtest_dataset_manifest.json` is suitable as the dataset contract for the next V15.2 backtest task.
3. If approved, please provide the next development task. If this is enough, explicitly say the project is complete.
