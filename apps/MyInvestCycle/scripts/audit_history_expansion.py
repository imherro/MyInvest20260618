from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data_expansion.coverage_planner import TARGET_END, TARGET_START
from data_expansion.expansion_audit import DEFAULT_OUTPUT_PATH, build_history_expansion_audit, write_history_expansion_audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit V2.6.2 historical data expansion coverage.")
    parser.add_argument("--start", default=TARGET_START, help="Target validation start date, YYYYMMDD.")
    parser.add_argument("--end", default=TARGET_END, help="Target validation end date, YYYYMMDD.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_history_expansion_audit(target_start=args.start, target_end=args.end)
    output = write_history_expansion_audit(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "target": payload["target"],
                "after": payload["after"],
                "coverage_status": payload["coverage_status"],
                "full_cycle_ready": payload["full_cycle_ready"],
                "known_gaps": payload["known_gaps"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
