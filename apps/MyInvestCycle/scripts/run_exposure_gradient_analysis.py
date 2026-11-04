from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_gradient_analysis import (
    DEFAULT_OUTPUT_PATH,
    build_exposure_gradient_analysis,
    write_exposure_gradient_analysis,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.10 exposure context risk/opportunity gradient analysis.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_exposure_gradient_analysis()
    output = write_exposure_gradient_analysis(payload, args.output)
    summary = payload["summary"]
    separation = summary["separation_review"]
    print(
        "V5.10 exposure gradient analysis written to "
        f"{output} | rows={summary['balanced_usable_rows']} "
        f"risk_sep={separation['risk_gradient_separation']} "
        f"opp_sep={separation['opportunity_gradient_separation']}"
    )


if __name__ == "__main__":
    main()
