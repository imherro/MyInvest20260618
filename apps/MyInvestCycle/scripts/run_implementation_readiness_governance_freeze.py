from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.governance_freeze import (
    DEFAULT_OUTPUT_PATH,
    build_implementation_readiness_governance_freeze,
    validate_implementation_readiness_governance_freeze,
    write_implementation_readiness_governance_freeze,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V13.4 implementation readiness governance freeze.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_implementation_readiness_governance_freeze()
    audit = validate_implementation_readiness_governance_freeze(payload)
    output = write_implementation_readiness_governance_freeze(payload, args.output)
    summary = payload["summary"]
    print(
        "V13.4 implementation readiness governance freeze written to "
        f"{output} | freeze={summary['governance_freeze_status']} "
        f"stages={summary['frozen_stage_count']} "
        f"candidate={summary['implementation_candidate_status']} "
        f"ready={summary['implementation_ready']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
