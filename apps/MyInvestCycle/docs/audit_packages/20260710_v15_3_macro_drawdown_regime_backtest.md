请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V15.3 Macro Drawdown Regime Baseline Backtest Audit Package

## Task

TASK V15.3 - Macro + Drawdown Regime Baseline Backtest.

V15.3 runs the first real research backtest after V15.0-V15.2. It tests whether long-term macro cycle plus drawdown context improves a broad-index strategy versus cash, CSI 300 buy-hold, Shanghai Composite buy-hold and the old strategy baseline.

This is research-only. It does not generate production signals, positions, trade orders, broker actions or intraday instructions.

## Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Previous audited V15.2 commit: `e5e8d79c4e8e2a530975c8075b5326ee51e58238`
- Expected commit title: `Add V15.3 macro drawdown baseline backtest`

## Added Files

- `strategy_rebase/macro_drawdown_backtest.py`
- `scripts/run_v15_macro_drawdown_backtest.py`
- `scripts/test_v15_macro_drawdown_backtest.py`
- `data/v15_macro_drawdown_backtest_result.json`
- `docs/strategy_rebase/v15_3_macro_drawdown_regime_backtest.md`
- `docs/audit_packages/20260710_v15_3_macro_drawdown_regime_backtest.md`

## Modified Files

- `strategy_rebase/__init__.py`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`

## Strategy Contract

Carrier:

- `000300.SH` CSI 300 close series

Signal timing:

- Macro phase and CSI 300 drawdown are observed after close on day `t`.
- Exposure is applied to day `t+1` return.

Exposure rules:

- `EARLY_CYCLE` / `EXPANSION`: 85% base, 100% if CSI 300 drawdown <= -8%.
- `ROTATION`: 65% base, 75% if drawdown <= -10%.
- `LATE_CYCLE`: 55% base, 30% if drawdown <= -5%.
- `CONTRACTION`: 25% base, 15% if drawdown <= -5%.
- `UNKNOWN`: 50%.

Cash assumption:

- 2.0% annualized, converted to daily return with 252 trading days.

## Output Contract

Generated artifact:

- `data/v15_macro_drawdown_backtest_result.json`

Required top-level flags:

- `phase = V15.3`
- `backtest_status = completed`
- `research_backtest_only = true`
- `not_production_signal = true`
- `no_real_trade_order = true`
- `strategy_scope = macro_drawdown_regime_baseline`
- `uses_point_in_time_inputs = true`
- `uses_t_plus_one_execution = true`

Required constraints:

- `no_broker_connection = true`
- `no_order_generation = true`
- `not_intraday_signal = true`
- `not_production_trade_signal = true`

Required benchmarks:

- `cash_baseline`
- `csi_300_buy_hold`
- `shanghai_composite_buy_hold`
- `old_strategy_baseline`

Required strategy metrics:

- `total_return`
- `CAGR`
- `annual_return`
- `annual_alpha`
- `max_drawdown`
- `calmar`
- `sharpe`
- `yearly_returns`
- `regime_segment_returns`
- `drawdown_recovery_days`

## Current Full-Window Result

Backtest period:

- `20150105` to `20260708`
- 2,796 sessions

Macro drawdown strategy:

- total return: `50.38%`
- CAGR / annual return: `3.75%`
- annual alpha vs CSI 300: `1.31%`
- max drawdown: `-35.92%`
- Calmar: `0.104321`
- Sharpe: `0.185568`
- drawdown recovery days: `1,264`

Benchmarks over the same full window:

- cash baseline CAGR: `2.02%`
- CSI 300 buy-hold CAGR: `2.44%`, max drawdown `-46.70%`, Calmar `0.052159`
- Shanghai Composite buy-hold CAGR: `1.54%`, max drawdown `-52.30%`, Calmar `0.029510`

Comparison:

- beats cash baseline: `true`
- beats CSI 300 buy-hold: `true`
- beats Shanghai Composite buy-hold: `true`
- improves max drawdown vs CSI 300: `true`
- improves Calmar vs CSI 300: `true`

## Old Strategy Common-Period Comparison

Old strategy baseline is only available from `20200103` to `20260626`, so it is not mixed into the full 2015-2026 benchmark.

Common period:

- `20200103` to `20260626`

Macro drawdown strategy:

- CAGR: `3.83%`
- max drawdown: `-25.60%`
- Calmar: `0.149599`

Old strategy baseline:

- CAGR: `4.83%`
- max drawdown: `-14.33%`
- Calmar: `0.337013`

Interpretation: V15.3 improves over broad-index and cash baselines on the full window, but it does not beat the old strategy baseline on the shorter common period. It should not be packaged as a finished strategy.

## Web/API Exposure

- Added `GET /api/strategy-rebase/v15-macro-drawdown-backtest`
- Added the endpoint to `GET /api`
- Added compact summary key `v15_macro_drawdown_backtest` to `GET /api/results/summary?compact=true`
- Added `/validation` card title `V15.3 宏观回撤基准回测`

## Verification

Passed locally:

```text
python scripts\run_v15_macro_drawdown_backtest.py
python scripts\test_v15_macro_drawdown_backtest.py
python scripts\test_v15_backtest_dataset_materializer.py
python scripts\test_v15_backtest_dataset_builder.py
python scripts\test_v15_strategy_direction_rebase.py
python -m py_compile strategy_rebase\__init__.py strategy_rebase\macro_drawdown_backtest.py scripts\run_v15_macro_drawdown_backtest.py scripts\test_v15_macro_drawdown_backtest.py web\app.py
node --check web\static\dashboard.js
python -m compileall strategy_rebase scripts web
python scripts\test_risk_diagnostic_shadow_evidence_dashboard.py
python scripts\test_risk_diagnostic_shadow_event_input_package.py
python scripts\test_risk_diagnostic_shadow_first_event_workflow.py
python scripts\test_research_to_implementation_boundary.py
```

Observed generator output:

```text
V15.3 macro drawdown baseline backtest written to C:\Users\kunpeng\Documents\MyInvestCycle\data\v15_macro_drawdown_backtest_result.json | phase=V15.3 status=completed period=20150105..20260708 CAGR=3.75% alpha=1.31% max_drawdown=-35.92% calmar=0.104321 beats_cash=True beats_csi300=True trade=False audit=passed
```

8021 smoke test passed:

- `/api/strategy-rebase/v15-macro-drawdown-backtest` returned 200
- `phase = V15.3`
- `backtest_status = completed`
- `start_date = 20150105`
- `end_date = 20260708`
- strategy CAGR = `0.037469`
- annual alpha = `0.013113`
- max drawdown = `-0.359169`
- `audit_status = passed`
- `/api` includes `/api/strategy-rebase/v15-macro-drawdown-backtest`
- `/api/results/summary?compact=true` includes `v15_macro_drawdown_backtest`
- `/validation` includes card title `V15.3 宏观回撤基准回测`

Rendered browser check passed:

- card title visible
- annual return label visible
- research-only boundary visible
- no-trade boundary visible

## Known Local State

- `data/structural_survival_dataset.json` was already locally modified before this V15.3 task. It is unrelated and intentionally left unstaged/uncommitted.

## Review Questions

1. Please verify that V15.3 is only a research backtest and does not generate production trading signals or orders.
2. Please verify whether the broad-index macro/drawdown baseline is methodologically acceptable as a first benchmark.
3. Please decide whether the low absolute CAGR and weak common-period comparison versus the old baseline mean V15.4 should focus on structural bull/industry rotation alpha instead of more broad-index exposure tuning.
4. If approved, please provide the next development task. If this is enough, explicitly say the project is complete.
