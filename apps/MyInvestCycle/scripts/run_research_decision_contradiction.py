from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from decision_research.research_decision_contradiction import (
    DEFAULT_OUTPUT_PATH,
    build_research_decision_contradiction,
    write_research_decision_contradiction,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V8.3 research decision contradiction attribution.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_research_decision_contradiction()
    output = write_research_decision_contradiction(payload, args.output)
    summary = payload["summary"]
    print(
        "V8.3 research decision contradiction written to "
        f"{output} | focus={summary['focus_scenario_count']} "
        f"attribution={summary['attribution_count']} "
        f"types={summary['contradiction_type_counts']} "
        f"conclusion={summary['conclusion']}"
    )


if __name__ == "__main__":
    main()
