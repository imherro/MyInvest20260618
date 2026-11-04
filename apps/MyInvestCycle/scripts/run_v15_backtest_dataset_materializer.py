from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_backtest_dataset_materialization_status,
    write_v15_backtest_dataset_materialization_status,
)


def main() -> None:
    payload = build_v15_backtest_dataset_materialization_status()
    output = write_v15_backtest_dataset_materialization_status(payload)
    summary = payload["summary"]
    print(
        "V15.2 backtest dataset materialization status written to "
        f"{output} | phase={summary['phase']} "
        f"status={summary['materialization_status']} "
        f"groups={summary['dataset_groups_checked']} "
        f"sources={summary['available_source_count']}/{summary['source_count']} "
        f"full_dataset_fetched={summary['full_dataset_fetched']} "
        f"strategy_run={summary['strategy_run']} "
        f"position_generated={summary['position_generated']} "
        f"trade_signal_generated={summary['trade_signal_generated']} "
        f"trade={summary['production_trade_enabled']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
