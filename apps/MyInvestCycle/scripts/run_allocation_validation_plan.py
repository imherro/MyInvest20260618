from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_validation_plan_audit import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_validation_plan,
    validate_allocation_validation_plan,
    write_allocation_validation_plan,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and audit V9.3 allocation validation plan.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_allocation_validation_plan()
    audit = validate_allocation_validation_plan(payload)
    output = write_allocation_validation_plan(payload, args.output)
    summary = payload["summary"]
    print(
        "V9.3 allocation validation plan written to "
        f"{output} | plans={summary['validation_plan_count']} "
        f"executed={summary['executed_plan_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
