请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V14.7 Risk Diagnostic Shadow Observation First Event Workflow

## Task

Build the first manual shadow event workflow for `risk_diagnostic_layer`.

This task defines the complete human-driven flow from a manual event JSON to schema validation, source hash validation, duplicate check, no-trade check, quality audit queue, and later outcome review placeholder. It must not automatically create an event, scan markets, judge risk, adjust exposure or positions, map ETFs, generate weights, allocate, trade, create orders, or connect to a broker.

## GitHub Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Expected commit title: `Add V14.7 risk diagnostic first event workflow`

## Code Audit Scope

New / changed files:

- `risk_diagnostic_shadow/first_event_workflow.py`
- `risk_diagnostic_shadow/__init__.py`
- `scripts/run_risk_diagnostic_shadow_first_event_workflow.py`
- `scripts/test_risk_diagnostic_shadow_first_event_workflow.py`
- `data/risk_diagnostic_shadow_first_event_workflow.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v14_7_risk_diagnostic_shadow_first_event_workflow.md`

Input artifacts:

- `data/risk_diagnostic_shadow_observation_log.json`
- `data/risk_diagnostic_shadow_manual_event_capture.json`
- `data/risk_diagnostic_shadow_event_quality_audit.json`

## Result Summary

Generated artifact:

- `data/risk_diagnostic_shadow_first_event_workflow.json`

Key output:

- `component_id`: `risk_diagnostic_layer`
- `workflow_status`: `ready_for_first_manual_event`
- `event_count`: 0
- `quality_queue_count`: 0
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
- `conclusion`: `risk_diagnostic_shadow_first_event_workflow_ready_no_event_no_trade`

Workflow steps:

1. manual event JSON preparation
2. schema validation
3. source hash validation
4. duplicate check
5. no-trade check
6. quality audit queue
7. later outcome review placeholder

Current status:

- No shadow event exists.
- The quality audit queue is empty.
- No automatic market scan is enabled.
- No automatic event is generated.
- No automatic risk judgment is performed.
- No trade path is enabled.

## Web/API Exposure

New API:

- `GET /api/implementation-readiness/risk-diagnostic-shadow-first-event-workflow`

Also included in:

- `GET /api`
- `GET /api/results/summary?compact=true` as `risk_diagnostic_shadow_first_event_workflow`

Web page:

- `/validation`
- New card title: `风险诊断首个事件流程`

## Verification Commands

```powershell
python scripts\run_risk_diagnostic_shadow_first_event_workflow.py
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
python -m py_compile web\app.py risk_diagnostic_shadow\__init__.py risk_diagnostic_shadow\first_event_workflow.py risk_diagnostic_shadow\event_quality_audit.py risk_diagnostic_shadow\manual_event_capture.py risk_diagnostic_shadow\observation_framework.py risk_diagnostic_shadow\observation_logger.py risk_diagnostic_shadow\observation_review.py scripts\run_risk_diagnostic_shadow_first_event_workflow.py scripts\test_risk_diagnostic_shadow_first_event_workflow.py
node --check web\static\dashboard.js
python -m compileall implementation_boundary implementation_readiness risk_diagnostic_shadow external_validation allocation_research decision_research asset_opportunity scripts web
```

Smoke checks:

```text
GET /api/implementation-readiness/risk-diagnostic-shadow-first-event-workflow -> 200
GET /api/results/summary?compact=true -> contains risk_diagnostic_shadow_first_event_workflow
GET /api -> contains /api/implementation-readiness/risk-diagnostic-shadow-first-event-workflow
GET /validation -> contains 风险诊断首个事件流程
```

## Audit Questions For ChatGPT

1. Please verify with GitHub skill that V14.7 defines the first manual event workflow only.
2. Please confirm the current status is `ready_for_first_manual_event`, `event_count=0`, and `quality_queue_count=0`.
3. Please confirm no event is created and no quality queue item is fabricated.
4. Please confirm no automatic market scan, automatic event, automatic warning, automatic risk judgment, exposure adjustment, ETF mapping, portfolio weight, allocation, optimization result, trade signal, order, or broker connection is generated.
5. Please decide the next development task or explicitly say whether the project is complete.

## Known Boundary

V14.7 still does not make `risk_diagnostic_layer` implementation-ready. It only defines the human workflow needed before the first real shadow event is manually submitted.
