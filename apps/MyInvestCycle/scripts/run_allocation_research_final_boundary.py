from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_research_final_boundary import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_research_final_boundary,
    validate_allocation_research_final_boundary,
    write_allocation_research_final_boundary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V10.3 allocation research final boundary decision.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_allocation_research_final_boundary()
    audit = validate_allocation_research_final_boundary(payload)
    output = write_allocation_research_final_boundary(payload, args.output)
    summary = payload["summary"]
    print(
        "V10.3 allocation research final boundary written to "
        f"{output} | directions={summary['direction_count']} "
        f"external={summary['continue_external_validation_count']} "
        f"governance={summary['research_governance_only_count']} "
        f"frozen={summary['frozen_no_external_validation_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
