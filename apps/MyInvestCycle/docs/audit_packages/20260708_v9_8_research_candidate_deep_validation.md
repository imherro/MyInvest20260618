请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V9.8 Research Candidate Deep Validation Framework

## Scope

- Task: Research Candidate Deep Validation Framework.
- Purpose: deepen validation for V9.7 `continue_research` hypotheses H2 and H4.
- Boundary: research-only extended validation.
- Explicitly not produced: strategy, allocation, asset selection, ETF mapping, portfolio weight, exposure percent, optimization, trade signal, broker order.

## Fixed Inputs

- `data/research_candidate_promotion_gate.json`
- `data/allocation_experiment_phase1_validation.json`
- `data/research_decision_scenario_audit.json`
- `data/research_decision_contradiction.json`

## New / Changed Files

- `allocation_research/research_candidate_deep_validation.py`
- `allocation_research/__init__.py`
- `scripts/run_research_candidate_deep_validation.py`
- `scripts/test_research_candidate_deep_validation.py`
- `data/research_candidate_deep_validation.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v9_8_research_candidate_deep_validation.md`

Unrelated local file intentionally not included in the V9.8 commit:

- `data/structural_survival_dataset.json`

## Result Summary

- target_hypothesis_count: 2
- validation_result_count: 2
- supported_count: 1
- inconclusive_count: 1
- unsupported_count: 0

Rows:

- H2 `risk_dominant_protection_persistence`: `inconclusive`
  - V9.6/V9.7 still support continuing research.
  - Stricter V8 scenario stability check does not pass.
  - Evidence: low consistency count 3 of 6 scenarios, low consistency share 0.5, risk-axis lag / structural rotation missed count 1.
- H4 `contradiction_first_promotion_gate`: `supported`
  - Supported only as a research gate discipline.
  - Evidence: 5 focus scenarios, 5 attributions, 5 contradiction types, promotion blocked by V9.7.
  - Still no counterfactual strategy or allocation result.

Required false flags:

- `promotion_allowed=false`
- `strategy_promotion=false`
- `allocation_promotion=false`
- `investable_output=false`
- `investable_output_generated=false`
- `ready_for_asset_selection=false`
- `ready_for_etf_mapping=false`
- `ready_for_weight_generation=false`
- `ready_for_optimization=false`
- `ready_for_trade=false`

## API / Web Surface

- New API: `GET /api/allocation-research/research-candidate-deep-validation`
- Included in `GET /api`
- Included in `GET /api/results/summary?compact=true` as `research_candidate_deep_validation`
- Validation page: `/validation`
- New validation card title: `研究候选深度验证`

## Validation Commands

```powershell
python scripts\run_research_candidate_deep_validation.py
python scripts\test_research_candidate_deep_validation.py
python -m py_compile web\app.py allocation_research\__init__.py allocation_research\research_candidate_deep_validation.py scripts\run_research_candidate_deep_validation.py scripts\test_research_candidate_deep_validation.py
node --check web\static\dashboard.js
python -m compileall allocation_research decision_research asset_opportunity scripts web
```

API/browser smoke checks:

```text
GET /api/allocation-research/research-candidate-deep-validation -> 200
GET /api/results/summary?compact=true -> contains research_candidate_deep_validation
GET /api -> contains /api/allocation-research/research-candidate-deep-validation
GET /validation -> contains 研究候选深度验证
```

## Audit Questions For ChatGPT

1. Is it correct that H2 remains `inconclusive` under stricter cross-scenario stability?
2. Is it correct that H4 is `supported` only as a research-stage contradiction-first gate discipline?
3. Are the V8 scenario audit and contradiction attribution used without recomputing features or returns?
4. Is every investable output boundary still explicit and enforced?
5. Is the web/API exposure clear enough to prevent misreading V9.8 as a strategy signal?

## GitHub Review Request

Please use GitHub skill to inspect:

- repository: `https://github.com/imherro/MyInvestCycle`
- branch: `main`
- latest V9.8 commit after push
- full diff for the files listed above
- generated artifact: `data/research_candidate_deep_validation.json`
