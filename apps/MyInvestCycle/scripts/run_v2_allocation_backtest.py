from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.allocation_backtest_engine import DEFAULT_OUTPUT_PATH, run_v2_allocation_backtest, write_v2_allocation_backtest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V2 adaptive allocation validation backtest.")
    parser.add_argument("--start", default="20240101", help="Start date, YYYYMMDD.")
    parser.add_argument("--end", default="20991231", help="End date, YYYYMMDD.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--rebalance-every-sessions", type=int, default=20)
    parser.add_argument("--allow-fetch", action="store_true", help="Allow Tushare refresh for missing fund_daily ranges.")
    parser.add_argument("--refresh", action="store_true", help="Refresh benchmark price cache when --allow-fetch is set.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_v2_allocation_backtest(
        start_date=args.start,
        end_date=args.end,
        rebalance_every_sessions=args.rebalance_every_sessions,
        cache_only=not args.allow_fetch,
        refresh=args.refresh,
    )
    output = write_v2_allocation_backtest(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "summary": payload["summary"],
                "validation": payload["validation"],
                "data_quality": payload["data_quality"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
