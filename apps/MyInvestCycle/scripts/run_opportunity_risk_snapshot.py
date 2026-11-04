from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.opportunity_risk_classifier import (
    DEFAULT_END_DATE,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_START_DATE,
    build_opportunity_risk_snapshot,
    write_opportunity_risk_snapshot,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V4.3 opportunity/risk state separation snapshot.")
    parser.add_argument("--start", default=DEFAULT_START_DATE, help="Historical replay start date, YYYYMMDD.")
    parser.add_argument("--end", default=DEFAULT_END_DATE, help="Historical replay end date, YYYYMMDD.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_opportunity_risk_snapshot(start_date=args.start, end_date=args.end)
    output = write_opportunity_risk_snapshot(payload, args.output)
    summary = payload["historical_summary"]
    current = payload["current"]
    print(
        "V4.3 opportunity/risk snapshot written to "
        f"{output} | current={current['combined_state']} "
        f"replay_count={summary['replay_count']}"
    )


if __name__ == "__main__":
    main()
