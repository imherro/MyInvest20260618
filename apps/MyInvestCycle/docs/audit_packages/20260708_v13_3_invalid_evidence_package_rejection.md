请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V13.3 Invalid Evidence Package Rejection Test

## Task

Create a synthetic invalid evidence package case and prove the V13.2 validator rejects it.

This task intentionally does not submit real strategy evidence, evaluate real strategy returns, generate a strategy, select assets, map ETFs, create portfolio weights, generate allocations, optimize parameters, produce trade signals, create orders, or connect to a broker.

## GitHub Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Expected commit title: `Add V13.3 invalid evidence rejection`

## Fixed Input Artifacts

- `data/evidence_package_validation_engine.json`
- `data/research_component_evidence_submission_protocol.json`

All input hashes are recorded in the generated V13.3 output metadata.

## New / Changed Files

- `implementation_readiness/__init__.py`
- `implementation_readiness/evidence_package_rejection_example.py`
- `scripts/run_invalid_evidence_package_rejection_example.py`
- `scripts/test_invalid_evidence_package_rejection_example.py`
- `data/invalid_evidence_package_rejection_example.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v13_3_invalid_evidence_package_rejection.md`

## Result Summary

Generated artifact:

- `data/invalid_evidence_package_rejection_example.json`

Key output:

- `example_status`: `generated`
- `example_package_kind`: `invalid_blocked_case`
- `package_status`: `invalid_missing_or_boundary_violation`
- `validation_decision`: `blocked_pending_manual_review_and_future_audit`
- `missing_item_count`: greater than zero
- `boundary_violation_count`: `2`
- `forbidden_output_detected`: true
- `market_code_pattern_found`: false
- `implementation_ready`: false
- `investable_output`: false
- `strategy_output_generated`: false
- `allocation_output_generated`: false
- `trade_ready`: false
- `conclusion`: `invalid_evidence_package_rejected_no_strategy_no_allocation`

Invalid example summary:

- `package_id`: `example_invalid_package`
- `component_id`: `allocation_alpha_layer`
- `example_only`: true
- `contains_real_market_code`: false
- `contains_real_weight`: false
- `redacted_forbidden_field_present`: true

Validator result:

- `package_present`: true
- `component_id_status`: `valid`
- `implementation_ready`: false
- `boundary_violations` include:
  - `missing_required_field`
  - `forbidden_output_key_detected`

Interpretation:

- V13.3 proves the validator rejects a synthetic invalid package.
- The package is blocked because required sections are missing and a forbidden output field is present.
- The example is redacted and contains no real market code, real weight, real return, allocation, or trade instruction.

## Web/API Exposure

New API:

- `GET /api/implementation-readiness/invalid-evidence-example`

Also included in:

- `GET /api`
- `GET /api/results/summary?compact=true` as `invalid_evidence_package_rejection_example`

Web page:

- `/validation`
- New card title: `不合格证据包拒绝测试`

## Verification Commands

```powershell
python scripts\run_invalid_evidence_package_rejection_example.py
python scripts\test_invalid_evidence_package_rejection_example.py
python scripts\test_evidence_package_validation_engine.py
python scripts\test_research_component_evidence_submission_protocol.py
python scripts\test_implementation_readiness_evidence_audit.py
python scripts\test_implementation_readiness_evidence_specification.py
python scripts\test_research_to_implementation_boundary.py
python -m py_compile web\app.py implementation_boundary\__init__.py implementation_boundary\research_to_implementation_boundary.py implementation_readiness\__init__.py implementation_readiness\evidence_specification.py implementation_readiness\evidence_audit.py implementation_readiness\evidence_submission_protocol.py implementation_readiness\evidence_package_validator.py implementation_readiness\evidence_package_rejection_example.py scripts\run_research_to_implementation_boundary.py scripts\test_research_to_implementation_boundary.py scripts\run_implementation_readiness_evidence_specification.py scripts\test_implementation_readiness_evidence_specification.py scripts\run_implementation_readiness_evidence_audit.py scripts\test_implementation_readiness_evidence_audit.py scripts\run_research_component_evidence_submission_protocol.py scripts\test_research_component_evidence_submission_protocol.py scripts\run_evidence_package_validation_engine.py scripts\test_evidence_package_validation_engine.py scripts\run_invalid_evidence_package_rejection_example.py scripts\test_invalid_evidence_package_rejection_example.py
node --check web\static\dashboard.js
python -m compileall implementation_boundary implementation_readiness external_validation allocation_research decision_research asset_opportunity scripts web
```

Smoke checks:

```text
GET /api/implementation-readiness/invalid-evidence-example -> 200
GET /api/results/summary?compact=true -> contains invalid_evidence_package_rejection_example
GET /api -> contains /api/implementation-readiness/invalid-evidence-example
GET /validation -> contains 不合格证据包拒绝测试
```

## Audit Questions For ChatGPT

1. Please verify with GitHub skill that V13.3 only creates a synthetic invalid evidence package test and does not submit real evidence.
2. Please confirm the validator rejects the example with `implementation_ready=false`.
3. Please confirm the example contains no real market code, no real weight, no real return, no allocation, and no trade instruction.
4. Please confirm no asset code, ETF code, portfolio weight, allocation instruction, optimization result, or trade signal is generated as an investable output.
5. Please decide the next development task or explicitly say whether the project is complete.

## Known Boundary

V13.3 does not complete the MyInvestCycle project. It only proves the evidence package validator rejects an invalid synthetic package.
