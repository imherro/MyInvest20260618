请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V15.0 Mainline Outcome-Oriented Strategy Rebase

## Task

Implement `TASK V15.0 — Mainline Outcome-Oriented Strategy Rebase` on `main`.

This is a direction-reset task only. It freezes V12-V14 as governance/evidence/shadow infrastructure and redirects V15+ development toward return-first, drawdown-constrained strategy backtesting.

## GitHub Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Previous passed commit: `58b5ab83398b0f6ed2adf5b4027f782fbd4b5303`
- Expected commit title: `Add V15.0 mainline outcome strategy rebase`

## Code Audit Scope

New files:

- `strategy_rebase/__init__.py`
- `strategy_rebase/outcome_objectives.py`
- `scripts/run_v15_strategy_direction_rebase.py`
- `scripts/test_v15_strategy_direction_rebase.py`
- `data/v15_strategy_direction_rebase.json`
- `docs/strategy_rebase/v15_0_mainline_outcome_strategy_rebase.md`
- `docs/audit_packages/20260710_v15_0_mainline_outcome_strategy_rebase.md`

Changed files:

- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`

Known unrelated local file:

- `data/structural_survival_dataset.json` remains unstaged and uncommitted.

## Result Summary

Generated artifact:

- `data/v15_strategy_direction_rebase.json`

Key fields:

- `phase`: `V15`
- `mainline_direction`: `outcome_oriented_strategy_rebase`
- `direction_status`: `rebase_declared`
- `primary_objective`: `maximize_return_and_alpha`
- `secondary_objective`: `control_max_drawdown`
- `tertiary_objective`: `improve_explainability`
- `frozen_tracks.v12_v14_governance_shadow.status`: `frozen_as_infrastructure`
- `frozen_tracks.v12_v14_governance_shadow.not_main_alpha_strategy`: true
- `production_trade_enabled`: false
- `broker_connection_enabled`: false
- `real_order_generation_enabled`: false
- `constraints.does_not_run_backtest`: true
- `constraints.does_not_generate_trade_signal`: true

V12-V14 are explicitly retained as governance/evidence/shadow infrastructure. They are not the active alpha strategy, not the portfolio engine and not the trade engine.

## Web/API Exposure

New API:

- `GET /api/strategy-rebase/v15-direction`

Also included in:

- `GET /api`
- `GET /api/results/summary?compact=true` as `v15_strategy_direction_rebase`

Web page:

- `/validation`
- New card title: `V15 主线收益策略重构`

## Verification Commands

```powershell
python scripts\run_v15_strategy_direction_rebase.py
python scripts\test_v15_strategy_direction_rebase.py
python -m py_compile strategy_rebase\__init__.py strategy_rebase\outcome_objectives.py scripts\run_v15_strategy_direction_rebase.py scripts\test_v15_strategy_direction_rebase.py web\app.py
node --check web\static\dashboard.js
python scripts\test_risk_diagnostic_shadow_evidence_dashboard.py
python scripts\test_risk_diagnostic_shadow_event_input_package.py
python scripts\test_risk_diagnostic_shadow_first_event_workflow.py
python scripts\test_research_to_implementation_boundary.py
python -m compileall strategy_rebase scripts web
```

Smoke checks:

```text
GET /api/strategy-rebase/v15-direction -> 200
GET /api -> contains /api/strategy-rebase/v15-direction
GET /api/results/summary?compact=true -> contains v15_strategy_direction_rebase
GET /validation -> contains V15 主线收益策略重构
```

## Smoke Result

```json
{
  "v15_status": 200,
  "phase": "V15",
  "direction": "outcome_oriented_strategy_rebase",
  "primary": "maximize_return_and_alpha",
  "secondary": "control_max_drawdown",
  "v12_v14_status": "frozen_as_infrastructure",
  "trade_enabled": false,
  "does_not_run_backtest": true,
  "api_has_v15": true,
  "summary_has_v15": true,
  "validation_status": 200,
  "validation_has_card": true,
  "errors": {}
}
```

## Audit Questions For ChatGPT

1. Please verify with GitHub skill that V15.0 is direction-rebase-only.
2. Please confirm V12-V14 are frozen as infrastructure and are not presented as the active alpha strategy.
3. Please confirm V15.0 does not run a backtest, generate positions, map ETFs, generate weights, allocate, create trade signals, create orders or connect to a broker.
4. Please confirm `data/structural_survival_dataset.json` was not staged or committed.
5. If V15.0 passes, please give the next task, expected to be `TASK V15.1 — Outcome-Oriented Backtest Dataset Builder`.
