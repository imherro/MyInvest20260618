# V15.3 Macro Drawdown Regime Baseline Backtest

## Purpose

V15.3 runs the first research-only backtest after the V15 strategy rebase.

It tests one core hypothesis: in early or middle bull regimes, broad-index drawdowns may be add-position opportunities; in late-cycle or contraction regimes, drawdowns should be treated more defensively.

This phase is not a production strategy release. It does not create orders, connect to a broker, produce intraday signals or tell the user to trade.

## Strategy Rule

Signal and return indices:

- `000300.SH` CSI 300 price index is used only for drawdown signals.
- `H00300.CSI` CSI 300 total return index is used for strategy returns and the buy-and-hold benchmark.
- The evaluation starts from the first common trading day in 2016.
- Every one-way absolute exposure change is charged 15bp.

Timing rule:

- Market phase and drawdown are observed after close on day `t`.
- The target exposure is applied to day `t+1` return.

Exposure rule:

- `EARLY_CYCLE` / `EXPANSION`: 85% base, 100% when CSI 300 drawdown is at least 8%.
- `ROTATION`: 65% base, 75% when drawdown is at least 10%.
- `LATE_CYCLE`: 55% base, 30% when drawdown is at least 5%.
- `CONTRACTION`: 25% base, 15% when drawdown is at least 5%.
- `UNKNOWN`: 50%.

Cash return assumption:

- 2.0% annualized cash baseline, converted to daily return with 252 trading days.

## Output

Generated artifact:

- `data/v15_macro_drawdown_backtest_result.json`

Primary API:

- `GET /api/strategy-rebase/v15-macro-drawdown-backtest`

Summary page:

- `/validation`, card title `V15.3 宏观回撤基准回测`

## Current Result

Formal backtest window:

- `20160104` to `20260708`
- 2,552 sessions

Macro drawdown strategy:

- Total return: 58.77%
- CAGR / annual return: 4.67%
- Annual alpha vs CSI 300 total return: -0.99%
- Max drawdown: -26.24%
- Calmar: 0.178
- Sharpe: 0.265
- Longest drawdown recovery days: 1,254

Benchmarks over the same full window:

- Cash baseline CAGR: 2.02%
- CSI 300 total return buy hold CAGR: 5.66%, max drawdown -41.56%

Old strategy baseline is only available from `20200103` to `20260626`, so it is compared separately in `common_period_comparison`.

## Interpretation

The V15.3 rule reduces maximum drawdown and improves Calmar versus CSI 300 total return, but it underperforms the dividend-reinvested benchmark by 0.99 percentage points annualized. The earlier positive alpha came from comparing against the price index and is superseded by this formal result. V15.3 fails promotion as a return strategy.

## Boundary

Required flags:

- `research_backtest_only = true`
- `not_production_signal = true`
- `no_real_trade_order = true`
- `constraints.no_broker_connection = true`
- `constraints.no_order_generation = true`
- `constraints.not_intraday_signal = true`
- `constraints.not_production_trade_signal = true`

If future variants underperform cash or broad-index benchmarks, that failure is acceptable evidence and must not be marketed as a success.
