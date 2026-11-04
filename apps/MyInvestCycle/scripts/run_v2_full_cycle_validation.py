from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.full_cycle_validation import (
    DEFAULT_OUTPUT_PATH,
    run_full_cycle_validation,
    write_full_cycle_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V2.6.1 historical coverage and full-cycle validation audit.")
    parser.add_argument("--start", default="20150101", help="Desired full-cycle start date, YYYYMMDD.")
    parser.add_argument("--end", default="20991231", help="Desired full-cycle end date, YYYYMMDD.")
    parser.add_argument("--rebalance-every-sessions", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_full_cycle_validation(
        desired_start=args.start,
        desired_end=args.end,
        rebalance_every_sessions=args.rebalance_every_sessions,
    )
    output = write_full_cycle_validation(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "metadata": payload["metadata"],
                "coverage": {
                    "can_cover_desired_window": payload["coverage_audit"]["can_cover_desired_window"],
                    "operational_validation_window": payload["coverage_audit"]["operational_validation_window"],
                    "blocker_count": payload["coverage_audit"]["blocker_count"],
                },
                "comparison": payload["comparison"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
