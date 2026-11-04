请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V14.8 First Manual Shadow Event Submission Input Package

## Task

Build the input package for the first manual `risk_diagnostic_layer` shadow event.

This task does not submit an event. It only provides the manual event template, JSON schema, and validation CLI. The CLI validates a user-supplied event file but does not append it to the observation log.

## GitHub Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Expected commit title: `Add V14.8 risk diagnostic event input package`

## Code Audit Scope

New / changed files:

- `risk_diagnostic_shadow/event_input_package.py`
- `risk_diagnostic_shadow/__init__.py`
- `scripts/run_risk_diagnostic_shadow_event_input_package.py`
- `scripts/validate_risk_diagnostic_shadow_event_input.py`
- `scripts/test_risk_diagnostic_shadow_event_input_package.py`
- `data/risk_diagnostic_shadow_event_input_package.json`
- `data/risk_diagnostic_shadow_event_input_template.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v14_8_risk_diagnostic_shadow_event_input_package.md`

Input artifact:

- `data/risk_diagnostic_shadow_first_event_workflow.json`

## Result Summary

Generated artifacts:

- `data/risk_diagnostic_shadow_event_input_package.json`
- `data/risk_diagnostic_shadow_event_input_template.json`

Key output:

- `component_id`: `risk_diagnostic_layer`
- `template_status`: `ready`
- `event_submitted`: false
- `validated_event_count`: 0
- `auto_scan_enabled`: false
- `auto_event_generation_enabled`: false
- `auto_decision_enabled`: false
- `auto_warning_enabled`: false
- `trade_enabled`: false
- `position_adjustment_enabled`: false
- `implementation_gate_result`: `blocked`
- `implementation_ready`: false
- `investable_output`: false
- `strategy_output_generated`: false
- `allocation_output_generated`: false
- `trade_ready`: false
- `conclusion`: `risk_diagnostic_shadow_event_input_template_ready_no_submission_no_trade`

Validation CLI:

```powershell
python scripts\validate_risk_diagnostic_shadow_event_input.py --event-file path\to\manual_event.json
```

The CLI returns:

- `valid_not_submitted` for a valid manual event file
- `invalid_event_file` for rejected input

It never appends to the observation log.

Current status:

- No event file was supplied.
- No event was submitted.
- No observation log event count changed.
- No automatic market scan is enabled.
- No automatic event is generated.
- No automatic risk judgment is performed.
- No trade path is enabled.

## Web/API Exposure

New API:

- `GET /api/implementation-readiness/risk-diagnostic-shadow-event-input-package`

Also included in:

- `GET /api`
- `GET /api/results/summary?compact=true` as `risk_diagnostic_shadow_event_input_package`

Web page:

- `/validation`
- New card title: `风险诊断事件输入包`

## Verification Commands

```powershell
python scripts\run_risk_diagnostic_shadow_event_input_package.py
python scripts\test_risk_diagnostic_shadow_event_input_package.py
python scripts\test_risk_diagnostic_shadow_first_event_workflow.py
python scripts\test_risk_diagnostic_shadow_event_quality_audit.py
python scripts\test_risk_diagnostic_shadow_manual_event_capture.py
python scripts\test_risk_diagnostic_shadow_observation_review.py
python scripts\test_risk_diagnostic_shadow_observation_log.py
python scripts\test_risk_diagnostic_shadow_framework.py
python scripts\test_risk_diagnostic_evidence_package.py
python scripts\test_implementation_readiness_governance_freeze.py
python scripts\test_invalid_evidence_package_rejection_example.py
python scripts\test_evidence_package_validation_engine.py
python scripts\test_research_component_evidence_submission_protocol.py
python scripts\test_implementation_readiness_evidence_audit.py
python scripts\test_implementation_readiness_evidence_specification.py
python scripts\test_research_to_implementation_boundary.py
python -m py_compile web\app.py risk_diagnostic_shadow\__init__.py risk_diagnostic_shadow\event_input_package.py risk_diagnostic_shadow\first_event_workflow.py risk_diagnostic_shadow\event_quality_audit.py risk_diagnostic_shadow\manual_event_capture.py risk_diagnostic_shadow\observation_framework.py risk_diagnostic_shadow\observation_logger.py risk_diagnostic_shadow\observation_review.py scripts\run_risk_diagnostic_shadow_event_input_package.py scripts\validate_risk_diagnostic_shadow_event_input.py scripts\test_risk_diagnostic_shadow_event_input_package.py
node --check web\static\dashboard.js
python -m compileall implementation_boundary implementation_readiness risk_diagnostic_shadow external_validation allocation_research decision_research asset_opportunity scripts web
```

Smoke checks:

```text
GET /api/implementation-readiness/risk-diagnostic-shadow-event-input-package -> 200
GET /api/results/summary?compact=true -> contains risk_diagnostic_shadow_event_input_package
GET /api -> contains /api/implementation-readiness/risk-diagnostic-shadow-event-input-package
GET /validation -> contains 风险诊断事件输入包
```

## Audit Questions For ChatGPT

1. Please verify with GitHub skill that V14.8 provides the input package only.
2. Please confirm `event_submitted=false` and `validated_event_count=0`.
3. Please confirm the validation CLI validates only and does not append an event.
4. Please confirm no automatic market scan, automatic event, automatic warning, automatic risk judgment, exposure adjustment, ETF mapping, portfolio weight, allocation, optimization result, trade signal, order, or broker connection is generated.
5. Please decide the next development task or explicitly say whether the project is complete.

## Known Boundary

V14.8 still does not make `risk_diagnostic_layer` implementation-ready. It prepares the first manual event submission package but waits for a real human-supplied event file.
