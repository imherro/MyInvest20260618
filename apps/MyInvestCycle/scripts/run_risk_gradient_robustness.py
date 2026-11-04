from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.risk_gradient_robustness import (
    DEFAULT_OUTPUT_PATH,
    build_risk_gradient_robustness,
    write_risk_gradient_robustness,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.11 risk gradient robustness and stability audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_risk_gradient_robustness()
    output = write_risk_gradient_robustness(payload, args.output)
    summary = payload["summary"]
    print(
        "V5.11 risk gradient robustness written to "
        f"{output} | rows={summary['source_rows']} "
        f"lift={summary['overall_high_risk_lift']} "
        f"consistency={summary['period_consistency']} "
        f"conclusion={summary['conclusion']}"
    )


if __name__ == "__main__":
    main()
