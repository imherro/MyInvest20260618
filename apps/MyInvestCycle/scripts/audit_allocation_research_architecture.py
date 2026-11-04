from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_research_boundary import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_research_architecture,
    validate_allocation_research_boundary,
    write_allocation_research_architecture,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit V9.1 allocation research architecture foundation.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_allocation_research_architecture()
    audit = validate_allocation_research_boundary(payload)
    output = write_allocation_research_architecture(payload, args.output)
    summary = payload["summary"]
    print(
        "V9.1 allocation research architecture written to "
        f"{output} | ready={summary['allocation_research_ready']} "
        f"context={summary['environment_context']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
