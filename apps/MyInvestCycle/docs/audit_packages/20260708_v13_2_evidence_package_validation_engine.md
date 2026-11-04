请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V13.2 Evidence Package Validation Engine

## Task

Build the validation engine for future implementation-readiness evidence packages.

This task intentionally does not accept a real evidence package in the current run, evaluate strategy returns, generate a strategy, select assets, map ETFs, create portfolio weights, generate allocations, optimize parameters, produce trade signals, create orders, or connect to a broker.

## GitHub Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Expected commit title: `Add V13.2 evidence package validator`

## Fixed Input Artifact

- `data/research_component_evidence_submission_protocol.json`

The input hash is recorded in the generated V13.2 output metadata.

## New / Changed Files

- `implementation_readiness/__init__.py`
- `implementation_readiness/evidence_package_validator.py`
- `scripts/run_evidence_package_validation_engine.py`
- `scripts/test_evidence_package_validation_engine.py`
- `data/evidence_package_validation_engine.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v13_2_evidence_package_validation_engine.md`

## Result Summary

Generated artifact:

- `data/evidence_package_validation_engine.json`

Key output:

- `validation_engine_status`: `defined`
- `current_package_status`: `invalid_not_submitted`
- `current_package_present`: false
- `implementation_gate_result`: `blocked`
- `component_template_count`: `8`
- `implementation_ready`: false
- `investable_output`: false
- `strategy_output_generated`: false
- `allocation_output_generated`: false
- `trade_ready`: false
- `conclusion`: `evidence_package_validation_engine_defined_no_strategy_no_allocation`

Validation engine:

- `current_run_accepts_real_package`: false
- `future_package_validation_supported`: true
- `can_promote_component_without_manual_review`: false

Supported checks:

- required field completeness
- component id membership
- input hash presence
- timestamp presence
- data lineage presence
- validation window presence
- manual review presence
- forbidden output key scan
- generic market code pattern scan

Current validation result:

- `package_status`: `invalid_not_submitted`
- `package_present`: false
- `component_id_status`: `not_checked`
- `implementation_ready`: false
- `validation_decision`: `blocked_no_package_submitted`

Interpretation:

- V13.2 defines the validation engine for future evidence packages.
- No real package is accepted or validated in this run.
- The current result is invalid because no package was submitted.
- No component is promoted.
- No investable output is generated.

## Web/API Exposure

New API:

- `GET /api/implementation-readiness/evidence-package-validator`

Also included in:

- `GET /api`
- `GET /api/results/summary?compact=true` as `evidence_package_validation_engine`

Web page:

- `/validation`
- New card title: `证据包校验引擎`

## Verification Commands

```powershell
python scripts\run_evidence_package_validation_engine.py
python scripts\test_evidence_package_validation_engine.py
python scripts\test_research_component_evidence_submission_protocol.py
python scripts\test_implementation_readiness_evidence_audit.py
python scripts\test_implementation_readiness_evidence_specification.py
python scripts\test_research_to_implementation_boundary.py
python -m py_compile web\app.py implementation_boundary\__init__.py implementation_boundary\research_to_implementation_boundary.py implementation_readiness\__init__.py implementation_readiness\evidence_specification.py implementation_readiness\evidence_audit.py implementation_readiness\evidence_submission_protocol.py implementation_readiness\evidence_package_validator.py scripts\run_research_to_implementation_boundary.py scripts\test_research_to_implementation_boundary.py scripts\run_implementation_readiness_evidence_specification.py scripts\test_implementation_readiness_evidence_specification.py scripts\run_implementation_readiness_evidence_audit.py scripts\test_implementation_readiness_evidence_audit.py scripts\run_research_component_evidence_submission_protocol.py scripts\test_research_component_evidence_submission_protocol.py scripts\run_evidence_package_validation_engine.py scripts\test_evidence_package_validation_engine.py
node --check web\static\dashboard.js
python -m compileall implementation_boundary implementation_readiness external_validation allocation_research decision_research asset_opportunity scripts web
```

Smoke checks:

```text
GET /api/implementation-readiness/evidence-package-validator -> 200
GET /api/results/summary?compact=true -> contains evidence_package_validation_engine
GET /api -> contains /api/implementation-readiness/evidence-package-validator
GET /validation -> contains 证据包校验引擎
```

## Audit Questions For ChatGPT

1. Please verify with GitHub skill that V13.2 only defines the validation engine and does not accept a real evidence package in the current run.
2. Please confirm the current package status is `invalid_not_submitted` and `implementation_ready=false`.
3. Please confirm the future validator scans schema, component id, hashes, timestamps, lineage, manual review, forbidden output keys, and generic market code patterns.
4. Please confirm no asset code, ETF code, portfolio weight, allocation instruction, optimization result, or trade signal is generated.
5. Please decide the next development task or explicitly say whether the project is complete.

## Known Boundary

V13.2 does not complete the MyInvestCycle project. It only defines a validator for future evidence packages. No real package is accepted or evaluated in this run.
