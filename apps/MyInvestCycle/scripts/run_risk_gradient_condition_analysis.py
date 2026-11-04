from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.risk_gradient_condition_analysis import (
    DEFAULT_OUTPUT_PATH,
    build_risk_gradient_condition_analysis,
    write_risk_gradient_condition_analysis,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.12 risk gradient conditional validation.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_risk_gradient_condition_analysis()
    output = write_risk_gradient_condition_analysis(payload, args.output)
    summary = payload["summary"]
    strongest = summary.get("strongest_positive_condition") or {}
    print(
        "V5.12 risk gradient condition analysis written to "
        f"{output} | rows={summary['source_rows']} "
        f"positive={summary['positive_condition_count']} "
        f"insufficient={summary['insufficient_condition_count']} "
        f"top={strongest.get('condition')}"
    )


if __name__ == "__main__":
    main()
