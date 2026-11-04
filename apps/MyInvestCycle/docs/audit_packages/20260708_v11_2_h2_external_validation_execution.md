请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V11.2 H2 External Validation Execution Framework

## Task

Execute the V11.1 pre-registered H2 external validation protocol using frozen risk evidence only.

This task intentionally does not recompute market features, calculate new forward returns, run a market backtest, optimize parameters, select assets, map ETFs, generate portfolio weights, create allocation output, emit trade signals, create orders, or connect to a broker.

## GitHub Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Expected commit title: `Add V11.2 H2 external validation execution`

## Fixed Input Artifacts

- `data/external_validation_protocol.json`
- `data/allocation_research_final_boundary.json`
- `data/risk_gradient_robustness.json`
- `data/risk_gradient_condition_analysis.json`
- `data/protection_score_validation.json`
- `data/two_axis_context_validation.json`
- `data/context_information_attribution.json`

All input hashes are recorded in the generated V11.2 output metadata.

## New / Changed Files

- `external_validation/validation_execution_framework.py`
- `external_validation/__init__.py`
- `scripts/run_h2_external_validation_execution.py`
- `scripts/test_h2_external_validation_execution.py`
- `data/h2_external_validation_execution.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v11_2_h2_external_validation_execution.md`

## Result Summary

Generated artifact:

- `data/h2_external_validation_execution.json`

Key output:

- `execution_status`: `completed`
- `target_hypothesis`: `H2`
- `window_count`: 4
- `passed_count`: 1
- `failed_count`: 0
- `inconclusive_count`: 3
- `overall_status`: `inconclusive`
- `promotion_allowed`: false
- `strategy_promotion`: false
- `allocation_ready`: false
- `investable_output`: false
- all asset/ETF/weight/optimization/trading readiness flags: false

Window results:

- `holdout_recent_window`: `inconclusive`
- `regime_transition_window`: `inconclusive`
- `structural_bull_window`: `inconclusive`
- `adverse_risk_window`: `passed`

Interpretation:

- H2 has visible adverse-risk evidence.
- H2 does not yet have broad external stability.
- H2 is not promoted into strategy, allocation, ETF mapping, weights, optimization, or trading.

## Web/API Exposure

New API:

- `GET /api/external-validation/execution-runs`

Also included in:

- `GET /api`
- `GET /api/results/summary?compact=true` as `h2_external_validation_execution`

Web page:

- `/validation`
- New card title: `H2 外部验证执行`

## Verification Commands

```powershell
python scripts\run_h2_external_validation_execution.py
python scripts\test_h2_external_validation_execution.py
python -m py_compile web\app.py external_validation\__init__.py external_validation\validation_execution_framework.py scripts\run_h2_external_validation_execution.py scripts\test_h2_external_validation_execution.py
node --check web\static\dashboard.js
python -m compileall external_validation allocation_research decision_research asset_opportunity scripts web
```

Smoke checks:

```text
GET /api/external-validation/execution-runs -> 200
GET /api/results/summary?compact=true -> contains h2_external_validation_execution
GET /api -> contains /api/external-validation/execution-runs
GET /validation -> contains H2 外部验证执行
```

## Audit Questions For ChatGPT

1. Please verify with GitHub skill that V11.2 only executes the pre-registered H2 validation protocol using frozen evidence and does not create investable output.
2. Please confirm that the overall `inconclusive` result is correctly conservative and does not promote H2.
3. Please confirm no asset code, ETF code, portfolio weight, allocation instruction, optimization result, or trade signal is generated.
4. Please decide the next development task or explicitly say whether the project is complete.

## Known Boundary

V11.2 is a research validation execution artifact. It is not a strategy and not a portfolio decision.
