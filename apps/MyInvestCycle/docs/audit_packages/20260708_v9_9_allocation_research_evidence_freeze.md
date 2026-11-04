请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V9.9 Allocation Research Evidence Freeze & Decision Boundary Summary

## Scope

- Task: Allocation Research Evidence Freeze & Decision Boundary Summary.
- Purpose: freeze V9.1-V9.8 allocation research evidence and decision boundaries.
- Boundary: research evidence freeze only.
- Explicitly not produced: strategy, allocation, asset selection, ETF mapping, portfolio weight, exposure percent, optimization, trade signal, broker order.

## Fixed Inputs

- `data/allocation_research_architecture.json`
- `data/allocation_research_hypotheses.json`
- `data/allocation_validation_plan.json`
- `data/allocation_experiment_templates.json`
- `data/allocation_experiment_results_phase0.json`
- `data/allocation_experiment_phase1_validation.json`
- `data/research_candidate_promotion_gate.json`
- `data/research_candidate_deep_validation.json`

## New / Changed Files

- `allocation_research/allocation_research_evidence_freeze.py`
- `allocation_research/__init__.py`
- `scripts/audit_allocation_research_evidence.py`
- `scripts/test_allocation_research_evidence_freeze.py`
- `data/allocation_research_evidence_freeze.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v9_9_allocation_research_evidence_freeze.md`

Unrelated local file intentionally not included in the V9.9 commit:

- `data/structural_survival_dataset.json`

## Result Summary

- research_state: `frozen`
- evidence_scope: `V9.1-V9.8`
- hypothesis_count: 4
- retained_research_direction_count: 2
- paused_research_direction_count: 2
- supported_research_only_count: 1
- inconclusive_research_count: 1

Hypothesis status:

- H1: `freeze`
- H2: `inconclusive`
- H3: `freeze`
- H4: `supported_research_only`

Decision boundary:

- Retain research directions: H2, H4.
- Pause research directions: H1, H3.
- Allowed next actions: read existing evidence, audit existing evidence consistency, prepare external review package.
- Prohibited next actions: add new state layer, add new hypothesis, add new explanation layer, generate strategy, generate allocation, map assets or ETFs, generate weights or trades.

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

- New API: `GET /api/allocation-research/evidence-freeze`
- Included in `GET /api`
- Included in `GET /api/results/summary?compact=true` as `allocation_research_evidence_freeze`
- Validation page: `/validation`
- New validation card title: `配置研究证据冻结`

## Validation Commands

```powershell
python scripts\audit_allocation_research_evidence.py
python scripts\test_allocation_research_evidence_freeze.py
python -m py_compile web\app.py allocation_research\__init__.py allocation_research\allocation_research_evidence_freeze.py scripts\audit_allocation_research_evidence.py scripts\test_allocation_research_evidence_freeze.py
node --check web\static\dashboard.js
python -m compileall allocation_research decision_research asset_opportunity scripts web
```

API/browser smoke checks:

```text
GET /api/allocation-research/evidence-freeze -> 200
GET /api/results/summary?compact=true -> contains allocation_research_evidence_freeze
GET /api -> contains /api/allocation-research/evidence-freeze
GET /validation -> contains 配置研究证据冻结
```

## Audit Questions For ChatGPT

1. Does V9.9 correctly freeze V9.1-V9.8 evidence without adding another research layer?
2. Are H1/H3 correctly paused and H2/H4 correctly retained only as research directions?
3. Is H4 clearly marked `supported_research_only` rather than strategy-ready?
4. Are all allocation/strategy/investable readiness flags false?
5. Is the web/API exposure clear enough to prevent misreading this as an allocation-ready state?

## GitHub Review Request

Please use GitHub skill to inspect:

- repository: `https://github.com/imherro/MyInvestCycle`
- branch: `main`
- latest V9.9 commit after push
- full diff for the files listed above
- generated artifact: `data/allocation_research_evidence_freeze.json`
