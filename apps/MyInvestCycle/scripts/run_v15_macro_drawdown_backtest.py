from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_macro_drawdown_backtest_result,
    write_v15_macro_drawdown_backtest_result,
)


def _percent(value: object) -> str:
    return "--" if not isinstance(value, (int, float)) else f"{value * 100:.2f}%"


def main() -> None:
    payload = build_v15_macro_drawdown_backtest_result()
    output = write_v15_macro_drawdown_backtest_result(payload)
    summary = payload["summary"]
    strategy = payload["strategy_results"]["macro_drawdown_strategy"]
    comparison = payload["comparison"]
    print(
        "V15.3 macro drawdown baseline backtest written to "
        f"{output} | phase={summary['phase']} "
        f"status={summary['backtest_status']} "
        f"period={summary['start_date']}..{summary['end_date']} "
        f"CAGR={_percent(strategy['CAGR'])} "
        f"alpha={_percent(strategy['annual_alpha'])} "
        f"max_drawdown={_percent(strategy['max_drawdown'])} "
        f"calmar={strategy['calmar']} "
        f"beats_cash={comparison['beats_cash_baseline']} "
        f"beats_csi300={comparison['beats_csi_300_buy_hold']} "
        f"trade={summary['no_real_trade_order'] is False} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
