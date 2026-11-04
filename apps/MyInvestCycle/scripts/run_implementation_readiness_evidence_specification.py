from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.evidence_specification import (
    DEFAULT_OUTPUT_PATH,
    build_implementation_readiness_evidence_specification,
    validate_implementation_readiness_evidence_specification,
    write_implementation_readiness_evidence_specification,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V12.2 implementation readiness evidence specification.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_implementation_readiness_evidence_specification()
    audit = validate_implementation_readiness_evidence_specification(payload)
    output = write_implementation_readiness_evidence_specification(payload, args.output)
    summary = payload["summary"]
    print(
        "V12.2 implementation readiness evidence specification written to "
        f"{output} | status={summary['readiness_specification_status']} "
        f"readiness={summary['implementation_readiness_status']} "
        f"components={summary['component_spec_count']} "
        f"global_gates={summary['global_gate_count']} "
        f"implementation_gate={summary['implementation_gate_result']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
