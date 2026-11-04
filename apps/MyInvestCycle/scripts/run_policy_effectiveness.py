from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.policy_effectiveness import (
    DEFAULT_OUTPUT_PATH,
    build_policy_effectiveness,
    write_policy_effectiveness,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V4.5 policy effectiveness validation.")
    parser.add_argument("--start", default="20150101", help="Validation start date, YYYYMMDD.")
    parser.add_argument("--end", default="20261231", help="Validation end date, YYYYMMDD; capped to today.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_policy_effectiveness(start_date=args.start, end_date=args.end)
    output = write_policy_effectiveness(payload, args.output)
    summary = payload["summary"]
    usefulness = summary["policy_usefulness"]
    print(
        "V4.5 policy effectiveness written to "
        f"{output} | usable_rows={summary['usable_rows']} "
        f"status={usefulness['status']} "
        f"contradiction_rate={summary['contradiction_audit']['contradiction_rate']}"
    )


if __name__ == "__main__":
    main()
