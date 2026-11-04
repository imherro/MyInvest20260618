from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.evidence_package_validator import (
    DEFAULT_OUTPUT_PATH,
    build_evidence_package_validation_engine,
    validate_evidence_package_validation_engine,
    write_evidence_package_validation_engine,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V13.2 evidence package validation engine.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_evidence_package_validation_engine()
    audit = validate_evidence_package_validation_engine(payload)
    output = write_evidence_package_validation_engine(payload, args.output)
    summary = payload["summary"]
    print(
        "V13.2 evidence package validation engine written to "
        f"{output} | engine={summary['validation_engine_status']} "
        f"package={summary['current_package_status']} "
        f"templates={summary['component_template_count']} "
        f"ready={summary['implementation_ready']} "
        f"gate={summary['implementation_gate_result']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
