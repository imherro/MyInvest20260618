from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_boundary.research_to_implementation_boundary import (
    DEFAULT_OUTPUT_PATH,
    build_research_to_implementation_boundary,
    validate_research_to_implementation_boundary,
    write_research_to_implementation_boundary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V12.1 research-to-implementation boundary design.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_research_to_implementation_boundary()
    audit = validate_research_to_implementation_boundary(payload)
    output = write_research_to_implementation_boundary(payload, args.output)
    summary = payload["summary"]
    gate = payload["implementation_entry_gate"]
    print(
        "V12.1 research-to-implementation boundary written to "
        f"{output} | boundary={summary['boundary_status']} "
        f"implementation={summary['implementation_phase']} "
        f"candidates={summary['implementation_candidate_count']} "
        f"blocked={summary['isolated_or_blocked_count']} "
        f"gate={gate['current_gate_result']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
