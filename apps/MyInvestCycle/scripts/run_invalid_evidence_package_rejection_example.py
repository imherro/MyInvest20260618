from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.evidence_package_rejection_example import (
    DEFAULT_OUTPUT_PATH,
    build_invalid_evidence_package_rejection_example,
    validate_invalid_evidence_package_rejection_example,
    write_invalid_evidence_package_rejection_example,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V13.3 invalid evidence package rejection example.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_invalid_evidence_package_rejection_example()
    audit = validate_invalid_evidence_package_rejection_example(payload)
    output = write_invalid_evidence_package_rejection_example(payload, args.output)
    summary = payload["summary"]
    print(
        "V13.3 invalid evidence package rejection example written to "
        f"{output} | status={summary['package_status']} "
        f"decision={summary['validation_decision']} "
        f"violations={summary['boundary_violation_count']} "
        f"ready={summary['implementation_ready']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
