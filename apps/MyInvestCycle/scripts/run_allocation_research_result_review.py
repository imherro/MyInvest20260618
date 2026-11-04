from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_research_result_review import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_research_result_review,
    validate_allocation_research_result_review,
    write_allocation_research_result_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V10.2 allocation research result review.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_allocation_research_result_review()
    audit = validate_allocation_research_result_review(payload)
    output = write_allocation_research_result_review(payload, args.output)
    summary = payload["summary"]
    print(
        "V10.2 allocation research result review written to "
        f"{output} | reviewed={summary['reviewed_hypothesis_count']} "
        f"continue={summary['continue_research_count']} "
        f"retain={summary['retain_research_only_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
