# MyInvestCycle System Architecture Freeze

Status: stable
Freeze date: 2026-06-25
Execution boundary: simulation only

## Purpose

MyInvestCycle is frozen as a regime-driven institutional decision simulation
engine. It converts market state into risk, portfolio, strategy, and execution
simulation outputs. It is not an alpha engine, broker gateway, live trading loop,
or stock-selection system.

## Frozen Layers

1. Market understanding
   - Module boundary: `engine/market_engine.py`, `core/features.py`,
     `core/breadth.py`, `core/liquidity.py`
   - Output: regime, confidence, and sub-scores.

2. Risk control
   - Module boundary: `core/regime_adapter.py`, `core/risk_score_engine.py`,
     `core/exposure_controller.py`
   - Policy: `rules/risk_policy.yaml`
   - Output: risk score, risk level, recommended exposure, action.

3. Portfolio allocation
   - Module boundary: `core/capital_controller.py`,
     `core/portfolio_allocator.py`
   - Policy: `rules/portfolio_policy.yaml`
   - Output: total exposure, cash ratio, strategy allocation.

4. Strategy governance
   - Module boundary: `core/strategy_filter.py`,
     `core/strategy_budget_allocator.py`, `core/strategy_router.py`
   - Policy: `rules/strategy_policy.yaml`
   - Output: enabled strategies, disabled reasons, strategy budgets.

5. Execution simulation
   - Module boundary: `core/execution_policy.py`,
     `core/order_intent_builder.py`, `core/execution_simulator.py`
   - Policy: `rules/execution_policy.yaml`
   - Output: execution intent and simulated orders.

## Data Flow

```text
Market data
  -> Regime engine
  -> Risk engine
  -> Portfolio allocator
  -> Strategy router
  -> Execution simulator
  -> Web/API/read-only audit outputs
```

## Boundary Rules

- No stock selection.
- No real order generation.
- No broker connection.
- No live trading loop.
- No model expansion inside the frozen decision pipeline.
- No policy change without version upgrade and audit note.
- Web/API surfaces must remain read-only.

## API Surface

- `/api/regime/current`
- `/api/portfolio/current`
- `/api/strategy/current`
- `/api/execution/current`
- `/api/system/snapshot`
- `/api/results/summary`

## Frozen Completion Standard

The system is complete for the current phase when:

- All five layers return valid outputs.
- Policy files are present and locked.
- Execution remains simulation-only.
- System integrity check passes.
- Web shows every active layer.
