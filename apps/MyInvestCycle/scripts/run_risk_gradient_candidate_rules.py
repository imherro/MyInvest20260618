from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.risk_gradient_candidate_rules import (
    DEFAULT_OUTPUT_PATH,
    build_risk_gradient_candidate_rules,
    write_risk_gradient_candidate_rules,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.13 risk gradient minimal rule candidate audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_risk_gradient_candidate_rules()
    output = write_risk_gradient_candidate_rules(payload, args.output)
    summary = payload["summary"]
    print(
        "V5.13 risk gradient candidate rules written to "
        f"{output} | candidates={summary['candidate_count']} "
        f"primary={summary['primary_research_candidate_count']} "
        f"ready={summary['ready_for_rule_count']} "
        f"conclusion={summary['conclusion']}"
    )


if __name__ == "__main__":
    main()
