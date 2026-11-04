from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.two_axis_context_validation import (
    DEFAULT_OUTPUT_PATH,
    build_two_axis_context_validation,
    write_two_axis_context_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V6.5 adaptive context two-axis validation.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_two_axis_context_validation()
    output = write_two_axis_context_validation(payload, args.output)
    summary = payload["summary"]
    print(
        "V6.5 two-axis context validation written to "
        f"{output} | rows={summary['joined_sample_count']} "
        f"risk_spread={summary['two_axis_risk_spread']} "
        f"opportunity_spread={summary['two_axis_opportunity_spread']} "
        f"participate_opp_lift={summary['participate_opportunity_lift']} "
        f"protect_risk_lift={summary['protect_but_participate_risk_lift']} "
        f"conclusion={summary['conclusion']}"
    )


if __name__ == "__main__":
    main()
