请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V14.5 Risk Diagnostic Shadow Event Manual Capture

## Task

Build the manual capture capability for future real `risk_diagnostic_layer` shadow observation events.

This task does not automatically create a warning event. It only exposes a manual append path that requires a user-supplied event JSON, validates source lineage and no-trade guardrails, checks duplicates, and keeps implementation blocked.

## GitHub Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Expected commit title: `Add V14.5 risk diagnostic manual capture`

## Code Audit Scope

New / changed files:

- `risk_diagnostic_shadow/manual_event_capture.py`
- `risk_diagnostic_shadow/observation_review.py`
- `risk_diagnostic_shadow/__init__.py`
- `scripts/run_risk_diagnostic_shadow_manual_event_capture.py`
- `scripts/test_risk_diagnostic_shadow_manual_event_capture.py`
- `data/risk_diagnostic_shadow_manual_event_capture.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v14_5_risk_diagnostic_shadow_manual_event_capture.md`

Input artifact:

- `data/risk_diagnostic_shadow_observation_log.json`

## Result Summary

Generated artifact:

- `data/risk_diagnostic_shadow_manual_event_capture.json`

Key output:

- `component_id`: `risk_diagnostic_layer`
- `manual_capture_status`: `ready_for_manual_input`
- `source_event_count`: 0
- `submitted_event_count`: 0
- `auto_trigger_enabled`: false
- `auto_warning_enabled`: false
- `trade_enabled`: false
- `position_adjustment_enabled`: false
- `implementation_gate_result`: `blocked`
- `implementation_ready`: false
- `investable_output`: false
- `strategy_output_generated`: false
- `allocation_output_generated`: false
- `trade_ready`: false
- `conclusion`: `risk_diagnostic_shadow_manual_capture_ready_no_event_no_trade`

Manual capture rules:

- Event input must be an explicit manual event JSON file.
- The status run submits no event by default.
- Required event fields follow the V14.2 event schema.
- Source lineage must include a 64-character `source_artifact_hash`.
- Duplicate detection uses `event_time`, `market_data_as_of`, `warning_event_type`, and `source_artifact_hash`.
- Captured events remain no-trade observations and require later manual review.

Current status:

- No event was submitted in this run.
- The production shadow observation log remains unchanged at 0 events.
- No automatic warning is generated.
- No automatic risk judgment is performed.
- No trade path is enabled.

## V14.4 Compatibility Update

`risk_diagnostic_shadow/observation_review.py` now supports the future state `events_pending_manual_review` if a real manual event is appended later.

This does not change the current generated V14.4 artifact:

- current review remains `no_events_available`
- current event count remains 0
- current reviewed count remains 0

## Web/API Exposure

New API:

- `GET /api/implementation-readiness/risk-diagnostic-shadow-manual-capture`

Also included in:

- `GET /api`
- `GET /api/results/summary?compact=true` as `risk_diagnostic_shadow_manual_event_capture`

Web page:

- `/validation`
- New card title: `风险诊断人工事件录入`

## Verification Commands

```powershell
python scripts\run_risk_diagnostic_shadow_manual_event_capture.py
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
python -m py_compile web\app.py risk_diagnostic_shadow\__init__.py risk_diagnostic_shadow\manual_event_capture.py risk_diagnostic_shadow\observation_framework.py risk_diagnostic_shadow\observation_logger.py risk_diagnostic_shadow\observation_review.py scripts\run_risk_diagnostic_shadow_manual_event_capture.py scripts\test_risk_diagnostic_shadow_manual_event_capture.py
node --check web\static\dashboard.js
python -m compileall implementation_boundary implementation_readiness risk_diagnostic_shadow external_validation allocation_research decision_research asset_opportunity scripts web
```

Smoke checks:

```text
GET /api/implementation-readiness/risk-diagnostic-shadow-manual-capture -> 200
GET /api/results/summary?compact=true -> contains risk_diagnostic_shadow_manual_event_capture
GET /api -> contains /api/implementation-readiness/risk-diagnostic-shadow-manual-capture
GET /validation -> contains 风险诊断人工事件录入
```

## Audit Questions For ChatGPT

1. Please verify with GitHub skill that V14.5 creates a manual capture capability only.
2. Please confirm the default status artifact submits zero events and does not alter the production observation log.
3. Please confirm future event append requires explicit manual JSON, source hash, duplicate detection, and no-trade guardrails.
4. Please confirm no automatic warning, automatic risk judgment, position/exposure adjustment, ETF mapping, portfolio weight, allocation, optimization result, trade signal, order, or broker connection is generated.
5. Please review whether the V14.4 compatibility update for `events_pending_manual_review` is acceptable.
6. Please decide the next development task or explicitly say whether the project is complete.

## Known Boundary

V14.5 still does not make `risk_diagnostic_layer` implementation-ready. It only provides the manual observation capture path needed to begin accumulating real shadow evidence later.
