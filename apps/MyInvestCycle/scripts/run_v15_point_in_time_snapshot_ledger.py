from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import build_v15_point_in_time_snapshot_ledger, write_v15_point_in_time_snapshot_ledger


def main() -> None:
    ledger, status = build_v15_point_in_time_snapshot_ledger()
    ledger_path, status_path = write_v15_point_in_time_snapshot_ledger(ledger, status)
    print(
        f"V15.6 ledger written to {ledger_path} and {status_path} | "
        f"dates={status['decision_date_count']} complete={status['snapshot_complete_count']} "
        f"eligible={status['strict_point_in_time_eligible_count']} hashes={status['hash_verified_count']} "
        f"valuation={status['valuation_snapshot_available_count']} backtest={status['backtest_allowed']}"
    )


if __name__ == "__main__":
    main()
