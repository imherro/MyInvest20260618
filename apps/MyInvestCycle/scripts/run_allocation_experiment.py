from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_experiment_runner import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_experiment_results,
    validate_allocation_experiment_results,
    write_allocation_experiment_results,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V9.5 allocation experiment Phase 0 checks.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_allocation_experiment_results()
    audit = validate_allocation_experiment_results(payload)
    output = write_allocation_experiment_results(payload, args.output)
    summary = payload["summary"]
    print(
        "V9.5 allocation experiment Phase 0 results written to "
        f"{output} | executed={summary['executed_experiment_count']} "
        f"design_pass={summary['design_pass_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
