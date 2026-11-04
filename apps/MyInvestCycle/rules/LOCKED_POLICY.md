# Locked Policy Manifest

Status: locked
Lock date: 2026-06-25

DO NOT MODIFY WITHOUT VERSION UPGRADE.

## Locked Files

- `rules/risk_policy.yaml`
- `rules/portfolio_policy.yaml`
- `rules/strategy_policy.yaml`
- `rules/execution_policy.yaml`

## Change Rule

Policy changes require:

1. Versioned change note.
2. Re-run of `scripts/system_integrity_check.py`.
3. Updated `logs/decision_trace.json`.
4. Web verification that the changed behavior is visible.
5. Explicit review that the system remains simulation-only.

## Permanent Boundaries

- Risk policy controls risk level and exposure bands.
- Portfolio policy controls total exposure, cash, and strategy allocation.
- Strategy policy controls strategy eligibility and strategy budget.
- Execution policy controls simulated actions only.
- No policy may enable broker connection, real order placement, or stock-level
  execution.
