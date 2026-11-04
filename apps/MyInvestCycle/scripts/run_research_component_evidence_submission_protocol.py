from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.evidence_submission_protocol import (
    DEFAULT_OUTPUT_PATH,
    build_research_component_evidence_submission_protocol,
    validate_research_component_evidence_submission_protocol,
    write_research_component_evidence_submission_protocol,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V13.1 research component evidence submission protocol.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_research_component_evidence_submission_protocol()
    audit = validate_research_component_evidence_submission_protocol(payload)
    output = write_research_component_evidence_submission_protocol(payload, args.output)
    summary = payload["summary"]
    print(
        "V13.1 research component evidence submission protocol written to "
        f"{output} | protocol={summary['protocol_status']} "
        f"submission={summary['submission_status']} "
        f"contracts={summary['component_contract_count']} "
        f"package_created={summary['evidence_package_created']} "
        f"gate={summary['implementation_gate_result']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
