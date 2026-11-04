请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V9.7 Research Candidate Promotion Gate Audit

## Scope

- Task: Research Candidate Promotion Gate Audit.
- Purpose: decide which V9.2 hypotheses may continue research, freeze, or reject for now.
- Boundary: this is a research-stage gate only.
- Explicitly not produced: strategy, allocation, asset selection, ETF mapping, portfolio weight, exposure percent, trade signal, broker order.

## Fixed Inputs

- `data/allocation_experiment_phase1_validation.json`
- `data/allocation_validation_plan.json`
- `data/allocation_experiment_templates.json`

## New / Changed Files

- `allocation_research/research_candidate_promotion_gate.py`
- `allocation_research/__init__.py`
- `scripts/run_research_candidate_promotion_gate.py`
- `scripts/test_research_candidate_promotion_gate.py`
- `data/research_candidate_promotion_gate.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v9_7_research_candidate_promotion_gate.md`

Unrelated local file intentionally not included in the V9.7 commit:

- `data/structural_survival_dataset.json`

## Result Summary

- gate_count: 4
- continue_research_count: 2
- freeze_count: 2
- reject_for_now_count: 0
- H1: inconclusive -> freeze
- H2: supported -> continue_research
- H3: inconclusive -> freeze
- H4: supported -> continue_research

Required false flags:

- `promotion_allowed=false`
- `strategy_promotion=false`
- `allocation_promotion=false`
- `investable_output=false`
- `investable_output_generated=false`
- `ready_for_asset_selection=false`
- `ready_for_etf_mapping=false`
- `ready_for_weight_generation=false`
- `ready_for_trade=false`

## API / Web Surface

- New API: `GET /api/allocation-research/research-candidate-gate`
- Included in `GET /api`
- Included in `GET /api/results/summary?compact=true` as `research_candidate_promotion_gate`
- Validation page: `/validation`
- New validation card title: `研究阶段门禁审计`

## Validation Commands

```powershell
python scripts\run_research_candidate_promotion_gate.py
python scripts\test_research_candidate_promotion_gate.py
python -m py_compile web\app.py allocation_research\__init__.py allocation_research\research_candidate_promotion_gate.py scripts\run_research_candidate_promotion_gate.py scripts\test_research_candidate_promotion_gate.py
node --check web\static\dashboard.js
python -m compileall allocation_research decision_research asset_opportunity scripts web
```

API/browser smoke checks:

```text
GET /api/allocation-research/research-candidate-gate -> 200
GET /api/results/summary?compact=true -> contains research_candidate_promotion_gate
GET /api -> contains /api/allocation-research/research-candidate-gate
GET /validation -> contains 研究阶段门禁审计
```

## Audit Questions For ChatGPT

1. Does V9.7 correctly implement only a research-stage gate?
2. Are H2/H4 allowed to continue research without strategy/allocation promotion?
3. Are H1/H3 correctly frozen instead of rejected or promoted?
4. Is every investable output boundary still explicit and enforced?
5. Is the web/API exposure clear enough to prevent misreading as a strategy signal?

## GitHub Review Request

Please use GitHub skill to inspect:

- repository: `https://github.com/imherro/MyInvestCycle`
- branch: `main`
- latest V9.7 commit after push
- full diff for the files listed above
- generated artifact: `data/research_candidate_promotion_gate.json`
