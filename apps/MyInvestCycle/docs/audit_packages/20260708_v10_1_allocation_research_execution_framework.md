请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V10.1 Allocation Research Execution Framework

## Scope

- Task: Allocation Research Execution Framework.
- Purpose: execute frozen allocation research experiments as reproducible research records.
- Boundary: research execution records only.
- Explicitly not produced: strategy, allocation, asset selection, ETF mapping, portfolio weight, exposure percent, optimization, trade signal, broker order.

## Fixed Inputs

- `data/allocation_research_evidence_freeze.json`
- `data/two_axis_context_validation.json`
- `data/opportunity_feature_attribution.json`
- `data/research_decision_context.json`
- `data/research_decision_scenario_audit.json`
- `data/research_decision_contradiction.json`

## New / Changed Files

- `allocation_research/allocation_research_execution_framework.py`
- `allocation_research/__init__.py`
- `scripts/run_allocation_research_execution.py`
- `scripts/test_allocation_research_execution_framework.py`
- `data/allocation_research_execution_runs.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v10_1_allocation_research_execution_framework.md`

Unrelated local file intentionally not included in the V10.1 commit:

- `data/structural_survival_dataset.json`

## Result Summary

- execution_phase: `V10.1`
- source_research_state: `frozen`
- run_count: 2
- completed_run_count: 2
- supported_count: 1
- inconclusive_count: 1
- unsupported_count: 0

Execution runs:

- H2:
  - run_id: `V10_1_H2_20260707`
  - status: `completed`
  - result: `inconclusive`
  - execution_scope: `frozen_evidence_replay`
  - reason: frozen evidence supports risk attention but not cross-scenario stability.
- H4:
  - run_id: `V10_1_H4_20260707`
  - status: `completed`
  - result: `supported`
  - execution_scope: `frozen_evidence_replay`
  - reason: frozen contradiction attribution supports research gate discipline only.

Input hashes:

- File-level input hashes are recorded in `metadata.input_hashes`.
- Each run has its own deterministic `input_hash`.

Required false flags:

- `promotion_allowed=false`
- `strategy_promotion=false`
- `allocation_ready=false`
- `investable_output=false`
- `investable_output_generated=false`
- `ready_for_asset_selection=false`
- `ready_for_etf_mapping=false`
- `ready_for_weight_generation=false`
- `ready_for_optimization=false`
- `ready_for_trade=false`

## API / Web Surface

- New API: `GET /api/allocation-research/execution-runs`
- Included in `GET /api`
- Included in `GET /api/results/summary?compact=true` as `allocation_research_execution`
- Validation page: `/validation`
- New validation card title: `配置研究执行框架`

## Validation Commands

```powershell
python scripts\run_allocation_research_execution.py
python scripts\test_allocation_research_execution_framework.py
python -m py_compile web\app.py allocation_research\__init__.py allocation_research\allocation_research_execution_framework.py scripts\run_allocation_research_execution.py scripts\test_allocation_research_execution_framework.py
node --check web\static\dashboard.js
python -m compileall allocation_research decision_research asset_opportunity scripts web
```

API/browser smoke checks:

```text
GET /api/allocation-research/execution-runs -> 200
GET /api/results/summary?compact=true -> contains allocation_research_execution
GET /api -> contains /api/allocation-research/execution-runs
GET /validation -> contains 配置研究执行框架
```

## Audit Questions For ChatGPT

1. Does V10.1 correctly create only reproducible research execution records?
2. Are H2/H4 the only executed frozen research experiments?
3. Are input hashes recorded sufficiently to audit reproducibility?
4. Is H4 still `supported` only as research gate discipline, not a strategy?
5. Are all allocation/strategy/investable readiness flags false?
6. Is the web/API exposure clear enough to prevent misreading this as allocation output?

## GitHub Review Request

Please use GitHub skill to inspect:

- repository: `https://github.com/imherro/MyInvestCycle`
- branch: `main`
- latest V10.1 commit after push
- full diff for the files listed above
- generated artifact: `data/allocation_research_execution_runs.json`
