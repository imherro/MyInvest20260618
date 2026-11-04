from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from style_allocation.historical_style_context import (
    DEFAULT_OUTPUT_PATH,
    audit_style_context_coverage,
    build_historical_style_context,
    write_historical_style_context,
    write_style_context_coverage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build V3.5.5 historical style context features.")
    parser.add_argument("--start", default="20150105")
    parser.add_argument("--end", default="20260708")
    parser.add_argument("--step", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--coverage-output", default=str(DEFAULT_OUTPUT_PATH.with_name("historical_style_context_coverage.json")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_historical_style_context(
        start_date=args.start,
        end_date=args.end,
        step_sessions=args.step,
        cache_only=True,
    )
    output = write_historical_style_context(payload, args.output)
    coverage = audit_style_context_coverage(payload)
    coverage_output = write_style_context_coverage(coverage, args.coverage_output)
    print(
        json.dumps(
            {
                "output": str(output),
                "coverage_output": str(coverage_output),
                "metadata": payload["metadata"],
                "coverage_summary": coverage["summary"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
