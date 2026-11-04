from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_research_evidence_freeze import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_research_evidence_freeze,
    validate_allocation_research_evidence_freeze,
    write_allocation_research_evidence_freeze,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit V9 allocation research evidence freeze.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_allocation_research_evidence_freeze()
    audit = validate_allocation_research_evidence_freeze(payload)
    output = write_allocation_research_evidence_freeze(payload, args.output)
    summary = payload["summary"]
    print(
        "V9.9 allocation research evidence freeze written to "
        f"{output} | state={summary['research_state']} "
        f"retained={summary['retained_research_direction_count']} "
        f"paused={summary['paused_research_direction_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
