from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.evidence_audit import (
    DEFAULT_OUTPUT_PATH,
    build_implementation_readiness_evidence_audit,
    validate_implementation_readiness_evidence_audit,
    write_implementation_readiness_evidence_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V12.3 implementation readiness evidence audit framework.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_implementation_readiness_evidence_audit()
    audit = validate_implementation_readiness_evidence_audit(payload)
    output = write_implementation_readiness_evidence_audit(payload, args.output)
    summary = payload["summary"]
    print(
        "V12.3 implementation readiness evidence audit written to "
        f"{output} | framework={summary['audit_framework_status']} "
        f"package={summary['evidence_package_status']} "
        f"components={summary['component_audit_count']} "
        f"ready={summary['implementation_ready_component_count']} "
        f"gate={summary['implementation_gate_result']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
