# V15.4 Audit Package: Macro + Drawdown Robustness

## Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Base commit: `53a65dec70acc4be6e97fb75daada70b502a044d`
- Expected commit title: `Add V15.4 macro drawdown robustness validation`

## Scope

V15.4 validates the already-completed V15.3 baseline with nine nearby parameter variants, three transaction-cost levels, and annual prior-data-only walk-forward selection. It does not change V15.3, add a live strategy, generate current portfolio weights, connect a broker, or create orders.

## Added Files

- `strategy_rebase/macro_drawdown_robustness.py`
- `scripts/run_v15_macro_drawdown_robustness.py`
- `scripts/test_v15_macro_drawdown_robustness.py`
- `data/v15_macro_drawdown_robustness_result.json`
- `docs/strategy_rebase/v15_4_macro_drawdown_robustness.md`
- `docs/audit_packages/20260720_v15_4_macro_drawdown_robustness.md`

## Modified Files

- `strategy_rebase/__init__.py`
- `web/app.py`
- `web/static/dashboard.js`
- `web/templates/validation.html`

## Key Results

- Parameter variants: `9`
- V15.3 default rank: `9 / 9`
- Default CAGR: `3.7469%`
- Best CAGR: `3.8742%`
- Worst CAGR: `3.5788%`
- CAGR range: `0.2954 percentage points`
- Calmar range: `0.008011`
- Parameter neighborhood stable: `true`
- Default parameter preferred: `false`
- Promotion ready: `false`

Walk-forward at `5bp` one-way cost:

- Period: test years `2020` through `2026`
- CAGR: `3.3127%`
- Annual alpha versus aligned CSI300: `0.9006%`
- Maximum drawdown: `-25.2230%`
- Calmar: `0.131338`
- Sharpe: `0.178318`
- Beats aligned CSI300 CAGR: `true`

## Timing And Data Caveat

- Every parameter variant uses day `t` phase/drawdown for day `t+1` exposure.
- Each walk-forward test year selects parameters only from earlier dates.
- V15.3 default CAGR reproduction error is `0.0`.
- Historical phase publication-time lineage is not independently verified.
- `strict_point_in_time_status = unverified` is intentional and blocks promotion.

## Web/API

- `GET /api/strategy-rebase/v15-macro-drawdown-robustness`
- Endpoint included in `GET /api`.
- Compact result included as `v15_macro_drawdown_robustness` in `GET /api/results/summary?compact=true`.
- `/validation` includes `V15.4 参数稳健性与样本外验证`.

## Verification

```powershell
python scripts\run_v15_macro_drawdown_robustness.py
python scripts\test_v15_macro_drawdown_robustness.py
python scripts\test_v15_macro_drawdown_backtest.py
python scripts\test_v15_backtest_dataset_materializer.py
python scripts\test_v15_backtest_dataset_builder.py
python scripts\test_v15_strategy_direction_rebase.py
python -m py_compile strategy_rebase\__init__.py strategy_rebase\macro_drawdown_backtest.py strategy_rebase\macro_drawdown_robustness.py scripts\run_v15_macro_drawdown_robustness.py scripts\test_v15_macro_drawdown_robustness.py web\app.py
node --check web\static\dashboard.js
python -m compileall strategy_rebase scripts web
```

## Known Local State

`data/structural_survival_dataset.json` was already locally modified before V15.4. It remains unstaged and uncommitted and is not used by the V15.4 builder.

## Audit Questions

1. Does the grid preserve the V15.3 default exactly and vary only threshold/exposure strength?
2. Does every simulation preserve `t+1` timing?
3. Does every walk-forward selection use only dates before its test year?
4. Is it correct to separate `parameter_neighborhood_stable=true` from `default_parameter_preferred=false`?
5. Is the explicit unverified historical phase point-in-time lineage sufficient to block promotion?
6. Should the next task be publication-time phase reconstruction plus a valuation/crowding late-cycle overlay?
