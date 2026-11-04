from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.policy_historical_validation import (
    DEFAULT_END_DATE,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_START_DATE,
    build_policy_historical_validation,
    write_policy_historical_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V4.2 risk budget historical validation.")
    parser.add_argument("--start", default=DEFAULT_START_DATE, help="Replay start date, YYYYMMDD.")
    parser.add_argument("--end", default=DEFAULT_END_DATE, help="Replay end date, YYYYMMDD.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_policy_historical_validation(start_date=args.start, end_date=args.end)
    output = write_policy_historical_validation(payload, args.output)
    summary = payload["summary"]
    print(
        "V4.2 policy validation written to "
        f"{output} | replay_count={summary['replay_count']} "
        f"contradictions={summary['contradiction_count']} "
        f"review_items={summary.get('review_item_count', 0)}"
    )


if __name__ == "__main__":
    main()
