from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.full_cycle_backtest import (
    DEFAULT_OUTPUT_PATH,
    run_full_cycle_backtest,
    write_full_cycle_backtest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V2.6.3 full-cycle walk-forward revalidation.")
    parser.add_argument("--start", default="20150105", help="Validation start date, YYYYMMDD.")
    parser.add_argument("--end", default="20991231", help="Validation end date, YYYYMMDD.")
    parser.add_argument("--rebalance-every-sessions", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--allow-fetch", action="store_true", help="Allow non-cache data fetches where engine supports them.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_full_cycle_backtest(
        desired_start=args.start,
        desired_end=args.end,
        rebalance_every_sessions=args.rebalance_every_sessions,
        cache_only=not args.allow_fetch,
    )
    output = write_full_cycle_backtest(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "metadata": payload["metadata"],
                "macro_gap_policy": payload["data_quality"]["macro_gap_policy"],
                "comparison": {
                    key: {
                        "label": item.get("label"),
                        "total_return": item.get("total_return"),
                        "annualized_return": item.get("annualized_return"),
                        "max_drawdown": item.get("max_drawdown"),
                        "average_exposure": item.get("average_exposure"),
                    }
                    for key, item in payload["comparison"].items()
                },
                "structural_bull_contribution": payload["structural_bull_contribution"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
