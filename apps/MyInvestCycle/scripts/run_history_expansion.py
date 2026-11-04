from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data_expansion.coverage_planner import MACRO_WARMUP_START, TARGET_END, TARGET_START
from data_expansion.expansion_audit import DEFAULT_OUTPUT_PATH, build_history_expansion_audit, write_history_expansion_audit
from data_expansion.history_backfill import run_history_backfill


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V2.6.2 historical data foundation expansion.")
    parser.add_argument("--start", default=TARGET_START, help="Target validation start date, YYYYMMDD.")
    parser.add_argument("--end", default=TARGET_END, help="Target validation end date, YYYYMMDD.")
    parser.add_argument("--macro-warmup-start", default=MACRO_WARMUP_START, help="Macro warmup start date.")
    parser.add_argument("--audit-only", action="store_true", help="Do not fetch data; only audit current local coverage.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    backfill_report = None
    if not args.audit_only:
        backfill_report = run_history_backfill(
            start_date=args.start,
            end_date=args.end,
            macro_warmup_start=args.macro_warmup_start,
        )
    payload = build_history_expansion_audit(
        target_start=args.start,
        target_end=args.end,
        backfill_report=backfill_report,
    )
    output = write_history_expansion_audit(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "target": payload["target"],
                "available_before": payload["available_before"],
                "after": payload["after"],
                "coverage_status": payload["coverage_status"],
                "full_cycle_ready": payload["full_cycle_ready"],
                "known_gaps": payload["known_gaps"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
