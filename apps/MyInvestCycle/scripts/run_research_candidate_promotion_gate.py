from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.research_candidate_promotion_gate import (
    DEFAULT_OUTPUT_PATH,
    build_research_candidate_promotion_gate,
    validate_research_candidate_promotion_gate,
    write_research_candidate_promotion_gate,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V9.7 research-stage gate audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_research_candidate_promotion_gate()
    audit = validate_research_candidate_promotion_gate(payload)
    output = write_research_candidate_promotion_gate(payload, args.output)
    summary = payload["summary"]
    print(
        "V9.7 research-stage gate audit written to "
        f"{output} | continue={summary['continue_research_count']} "
        f"freeze={summary['freeze_count']} "
        f"reject={summary['reject_for_now_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
