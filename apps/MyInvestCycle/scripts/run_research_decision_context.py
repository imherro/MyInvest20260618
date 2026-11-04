from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from decision_research.research_decision_context import (
    DEFAULT_OUTPUT_PATH,
    build_research_decision_context,
    write_research_decision_context,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V8.1 research decision integration context.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_research_decision_context()
    output = write_research_decision_context(payload, args.output)
    summary = payload["summary"]
    print(
        "V8.1 research decision context written to "
        f"{output} | context={summary['decision_context']} "
        f"posture={summary['research_posture']} "
        f"candidate={summary['opportunity_research_candidate_count']} "
        f"watch={summary['opportunity_watch_count']}"
    )


if __name__ == "__main__":
    main()
