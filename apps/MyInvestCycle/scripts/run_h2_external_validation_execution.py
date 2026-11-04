from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from external_validation.validation_execution_framework import (
    DEFAULT_OUTPUT_PATH,
    build_h2_external_validation_execution,
    validate_h2_external_validation_execution,
    write_h2_external_validation_execution,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V11.2 H2 external validation execution framework.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_h2_external_validation_execution()
    audit = validate_h2_external_validation_execution(payload)
    output = write_h2_external_validation_execution(payload, args.output)
    summary = payload["summary"]
    print(
        "V11.2 H2 external validation execution written to "
        f"{output} | overall={summary['overall_status']} "
        f"passed={summary['passed_count']} "
        f"failed={summary['failed_count']} "
        f"inconclusive={summary['inconclusive_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
