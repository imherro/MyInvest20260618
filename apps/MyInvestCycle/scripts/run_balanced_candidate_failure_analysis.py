from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.balanced_candidate_failure_analysis import (
    DEFAULT_OUTPUT_PATH,
    build_balanced_candidate_failure_analysis,
    write_balanced_candidate_failure_analysis,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.5 balanced candidate failure attribution.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_balanced_candidate_failure_analysis()
    output = write_balanced_candidate_failure_analysis(payload, args.output)
    summary = payload["summary"]
    print(
        "V5.5 balanced candidate attribution written to "
        f"{output} | ready_for_rule_change={summary['ready_for_rule_change']} "
        f"review_items={summary['review_item_count']}"
    )


if __name__ == "__main__":
    main()
