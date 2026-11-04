from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_research_execution_framework import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_research_execution_framework,
    validate_allocation_research_execution_framework,
    write_allocation_research_execution_framework,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V10.1 allocation research execution framework.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_allocation_research_execution_framework()
    audit = validate_allocation_research_execution_framework(payload)
    output = write_allocation_research_execution_framework(payload, args.output)
    summary = payload["summary"]
    print(
        "V10.1 allocation research execution records written to "
        f"{output} | runs={summary['run_count']} "
        f"supported={summary['supported_count']} "
        f"inconclusive={summary['inconclusive_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
