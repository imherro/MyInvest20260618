# V15.0 Mainline Outcome-Oriented Strategy Rebase

## Purpose

V15.0 resets the main development direction on `main`.

V12-V14 are retained as governance, evidence and shadow-observation infrastructure. They are not the active alpha strategy, not a portfolio engine and not a trade engine. They must not be used to claim investable performance without V15+ outcome-oriented backtesting.

The V15+ mainline returns to the original objective: build an A-share strategy system that improves return and controls drawdown.

## Development Objective

Primary objective: maximize return and alpha.

Secondary objective: control maximum drawdown.

Tertiary objective: improve explainability.

Any future strategy claim must be backed by explicit backtest evidence.

## Frozen Track

The V12-V14 governance and shadow evidence chain is frozen as infrastructure:

- allowed future use: research governance, implementation readiness checks, evidence audit, shadow observation recording
- disallowed future use: main alpha claim, portfolio allocation driver, automatic trade signal, production risk control without backtest

## New Strategy Hypotheses

V15+ must test these hypotheses before any strategy claim:

- long-term macro and valuation regime determines when equity risk should be embraced or reduced
- large drawdowns during early/mid bull markets may be add-position opportunities
- high-level drawdowns near late-cycle tops may be de-risking signals
- A-shares may enter structural bull markets where broad indices stagnate but leading sectors/themes rotate upward
- sector/theme strength, breadth, concentration and persistence should be tested as allocation signals

## Roadmap

- V15.0: mainline outcome-oriented strategy rebase
- V15.1: backtest dataset builder
- V15.2: macro plus drawdown regime strategy backtest
- V15.3: structural bull rotation strategy backtest
- V15.4: strategy comparison and kill criteria

## Constraints

V15.0 is a direction declaration only. It does not run a backtest, generate positions, map ETFs, generate portfolio weights, generate allocation output, create trade signals, create orders or connect to a broker.

Production trading remains disabled.
