from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from decision_research.research_decision_scenario_audit import (
    DEFAULT_OUTPUT_PATH,
    build_research_decision_scenario_audit,
    write_research_decision_scenario_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V8.2 research decision historical scenario audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_research_decision_scenario_audit()
    output = write_research_decision_scenario_audit(payload, args.output)
    summary = payload["summary"]
    print(
        "V8.2 research decision scenario audit written to "
        f"{output} | scenarios={summary['scenario_count']} "
        f"covered={summary['covered_scenario_count']} "
        f"consistency={summary['consistency_counts']} "
        f"conclusion={summary['conclusion']}"
    )


if __name__ == "__main__":
    main()
