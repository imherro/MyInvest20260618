from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_experiment_phase1_validation import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_experiment_phase1_validation,
    validate_allocation_experiment_phase1_validation,
    write_allocation_experiment_phase1_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V9.6 allocation experiment Phase 1 validation.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_allocation_experiment_phase1_validation()
    audit = validate_allocation_experiment_phase1_validation(payload)
    output = write_allocation_experiment_phase1_validation(payload, args.output)
    summary = payload["summary"]
    print(
        "V9.6 allocation experiment Phase 1 validation written to "
        f"{output} | supported={summary['supported_count']} "
        f"inconclusive={summary['inconclusive_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
