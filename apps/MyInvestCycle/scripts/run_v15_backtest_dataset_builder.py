from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import build_v15_backtest_dataset_manifest, write_v15_backtest_dataset_manifest


def main() -> None:
    payload = build_v15_backtest_dataset_manifest()
    output = write_v15_backtest_dataset_manifest(payload)
    summary = payload["summary"]
    groups = payload["dataset_groups"]
    print(
        "V15.1 backtest dataset manifest written to "
        f"{output} | phase={summary['phase']} "
        f"status={summary['dataset_status']} "
        f"groups={len(groups)} "
        f"no_strategy={summary['does_not_run_strategy']} "
        f"no_position={summary['does_not_generate_position']} "
        f"no_trade_signal={summary['does_not_generate_trade_signal']} "
        f"trade={summary['production_trade_enabled']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
