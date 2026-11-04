请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据我下面的摘要判断。

# V11.1 External Validation Research Protocol

## Task

Define an external validation research protocol for H2 only, based on the frozen V10.3 final boundary.

This task intentionally does not run validation, recompute features, calculate forward returns, backtest, optimize parameters, select assets, map ETFs, generate portfolio weights, create allocation output, emit trade signals, create orders, or connect to a broker.

## GitHub Repository

- Repository: `https://github.com/imherro/MyInvestCycle`
- Branch: `main`
- Expected commit title: `Add V11.1 external validation protocol`

## Fixed Input Artifact

- `data/allocation_research_final_boundary.json`

The input hash is recorded in the generated V11.1 output metadata.

## New / Changed Files

- `external_validation/__init__.py`
- `external_validation/validation_protocol_schema.py`
- `external_validation/validation_protocol_audit.py`
- `scripts/run_external_validation_protocol.py`
- `scripts/test_external_validation_protocol.py`
- `data/external_validation_protocol.json`
- `web/app.py`
- `web/templates/validation.html`
- `web/static/dashboard.js`
- `docs/audit_packages/20260708_v11_1_external_validation_protocol.md`

## Result Summary

Generated artifact:

- `data/external_validation_protocol.json`

Key output:

- `protocol_phase_status`: `defined`
- `target_hypothesis`: `H2`
- `target_direction_count`: 1
- `excluded_direction_count`: 3
- `protocol_ready_for_manual_external_validation`: true
- H1: excluded, frozen
- H3: excluded, frozen
- H4: research governance only, not prediction validation
- `promotion_allowed`: false
- `strategy_promotion`: false
- `allocation_ready`: false
- `investable_output`: false
- all asset/ETF/weight/optimization/trading readiness flags: false

Protocol contents:

- pre-registered validation windows
- fixed methods
- failure standards
- stop conditions
- time-safety constraints

Interpretation:

- H2 may move into a manual, pre-registered external validation protocol.
- H2 is not promoted into a strategy.
- H4 remains governance only.
- H1/H3 remain frozen.

## Web/API Exposure

New API:

- `GET /api/external-validation/protocol`

Also included in:

- `GET /api`
- `GET /api/results/summary?compact=true` as `external_validation_protocol`

Web page:

- `/validation`
- New card title: `外部验证协议`

## Verification Commands

```powershell
python scripts\run_external_validation_protocol.py
python scripts\test_external_validation_protocol.py
python -m py_compile web\app.py external_validation\__init__.py external_validation\validation_protocol_schema.py external_validation\validation_protocol_audit.py scripts\run_external_validation_protocol.py scripts\test_external_validation_protocol.py
node --check web\static\dashboard.js
python -m compileall external_validation allocation_research decision_research asset_opportunity scripts web
```

Smoke checks:

```text
GET /api/external-validation/protocol -> 200
GET /api/results/summary?compact=true -> contains external_validation_protocol
GET /api -> contains /api/external-validation/protocol
GET /validation -> contains 外部验证协议
```

## Audit Questions For ChatGPT

1. Please verify with GitHub skill that V11.1 only defines a protocol and does not run validation, optimize, or generate investable output.
2. Please confirm the only target is H2 and that H1/H3/H4 are not incorrectly reintroduced as prediction or allocation targets.
3. Please confirm `data/external_validation_protocol.json` records the V10.3 input hash and keeps result-based parameter changes forbidden.
4. Please decide the next development task or explicitly say whether the project is complete.

## Known Boundary

V11.1 is a research protocol definition, not a validation result and not a strategy. It is allowed to say how H2 should be externally validated later, but it is not allowed to produce portfolio decisions.
